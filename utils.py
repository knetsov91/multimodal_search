import os
import UnsupportedTypeException
from schemas.schemas import SearchResults
from fastapi.concurrency import run_in_threadpool
import io
import time
import torch.nn.functional as F
from pymilvus import MilvusClient, DataType, SearchResult
from transformers import AutoModel, AutoImageProcessor, AutoTokenizer, Qwen3VLForConditionalGeneration, AutoProcessor
import torch
from PIL import Image
from datetime import timedelta
import os
from fastapi import File, UploadFile
from minio import Minio
import json

os.environ["CUDA_VISIBLE_DEVICES"] = "0"
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

COLLECTION_NAME="cooking_3000"
MLLM_MODEL="Qwen/Qwen3-VL-4B-Instruct"
MODEL_PATH = os.getenv("MODEL_PATH", MLLM_MODEL)
MODEL_NAME = "openai/clip-vit-base-patch16"
TOP_K=20
BUCKET_NAME="images"
DATASET_PATH="/home/kosio/.cache/kagglehub/datasets/jeromeblanchet/recipeqa-nlp-dataset/versions/1"
MINIO_HOST=os.getenv("MINIO_HOST", "localhost")

device = torch.device('cuda' if torch.cuda.is_available() else "cpu")
minio_client = Minio(f"{MINIO_HOST}:9000", access_key="minioadmin", secret_key="minioadmin", secure=False)

text_tokenizer = None
image_processor= None
model = None

def load_retriever():
	model = AutoModel.from_pretrained(MODEL_NAME).to(device)
	image_processor = AutoImageProcessor.from_pretrained(MODEL_NAME)
	text_tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

def text_embedding(model, tokenizer, txt):
  inputs = tokenizer(txt, truncation=True, return_tensors="pt")
  inputs = {k:v.to(device) for k,v in inputs.items()}
  with torch.no_grad():
    output= model.get_text_features(**inputs)
    output = output.pooler_output
  return output

def image_embedding(model, processor, image_path):
  inputs = processor([Image.open(image_path)], return_tensors="pt")
  inputs["pixel_values"] = inputs['pixel_values'].to(device)
  with torch.no_grad():
    img_emb = model.get_image_features(**inputs)
    img_emb = img_emb.pooler_output
  return img_emb

def search_text(txt_emb, k):
	txt_emb_norm = F.normalize(txt_emb.cpu(), p=2, dim=-1).numpy().tolist()
	r = milvus_client.search(
		collection_name=COLLECTION_NAME,
		anns_field="text_emb",
		data=txt_emb_norm,
		limit=k,
		output_fields=["m_id","text", "img_name", "title"]
	)

	return r

def search_image(img_emb, k):
	img_emb_norm = F.normalize(img_emb.cpu(), p=2, dim=-1).numpy().tolist()

	res = milvus_client.search(
		collection_name=COLLECTION_NAME,
		anns_field="img_emb",
		data=img_emb_norm,
		limit=k,
		output_fields=["m_id", "text", "img_name", "title"])
	return res

def get_min_max(results):
	if not results:
		return 0.0, 1.0
	scores = [r['distance'] for r in results]
	return min(scores), max(scores)

def late_fusion_with_norm(image_list, text_list, K=TOP_K, alpha=0.5, threshold=50):

	if alpha > 1.0:
		raise Exception("Illegal alpha")
	raw_images = image_list[0] if len(image_list) > 0 else []
	raw_texts = text_list[0] if len(text_list) > 0 else []

	if len(image_list) == 0:
		alpha == 1.0
	if len(text_list) == 0:
		alpha == 0.0
	image_set = set()
	text_set  = set()

	min_i, max_i = get_min_max(raw_images)
	min_t, max_t = get_min_max(raw_texts)

	fused_results = {}

	for img in raw_images:
		m_id = img['m_id']
		image_set.add(m_id)
		norm_img = (img['distance'] - min_i) / (max_i - min_i + 1e-6)  # avoid division by zero
		img_score = (1 - alpha) *  norm_img
		fused_results[m_id] = {
			"score": img_score,
			"text": img['entity']['text'],
			"img_name": img['entity']['img_name'],
			"title": img['entity']['title']
		}

	for txt in raw_texts:
		m_id = txt['m_id']
		text_set.add(m_id)
		norm_txt = (txt['distance'] - min_t) / (max_t - min_t + 1e-6)
		txt_score = alpha * norm_txt
		if m_id in fused_results:
			fused_results[m_id]['score'] += txt_score
		else:
			fused_results[m_id] = {
				"score":txt_score,
				"text": txt['entity']['text'],
				"img_name": txt['entity']['img_name'],
				"title": txt['entity']['title']

			}

	sorted_res = sorted(fused_results.items(), key=lambda x: x[1]['score'], reverse=True)

	return {
		"result": sorted_res[:threshold]
	}

def rank(model, processor, search_image=None, result_image=None, search_text=None, recipe_title=None,
		  recipe_text=None):
	query = "Recipe title: {}\n. Recipe text: {}".format(recipe_title, recipe_text)

	search_image_file = Image.open(search_image)
	result_image_file = Image.open(result_image)
	prompt5 = f"""
Goal: Culinary Similarity Evaluation.
Task: Evaluate the relevance between the two images provided below.
- Compare [IMAGE_A] (request from user) with [IMAGE_B] (the recipe found).
- Also consider the Text: "{search_text}" (user query) vs Founded recipe text: "{recipe_title}\n{recipe_text}".
Criteria:
1. Ignore the presentation/setting (e.g. cake stand vs parchment paper).
2. Focus on: Core ingredients (chocolate, nuts, meat) and the food category.
3. A cake and chocolate cupcake share the same core ingredients (Chocolate).

Scale:
- 1.0: Exact match.
- 0.7-0.9: High similarity in core ingredients (e.g. both are chocolate-based desserts).
- 0.0: No shared ingredients or category (e.g., Chocolate vs Salad).

Return ONLY the score based on the above rules.
"""
	messages = [
		{
			"role": "user",
			"content": [

				{"type": "text", "text": "[IMAGE_A]: "},
				{"type": "image", "image": search_image_file},
				{"type": "text", "text": "\n[IMAGE_B]: "},
				{"type": "image", "image": result_image_file},
				{"type": "text", "text": f"\n{prompt5}"},

			]
		}
	]

	inputs = processor.apply_chat_template(
		messages,
		tokenize=False,
		add_generation_prompt=True
	)

	inputs = processor(max_pixels=512 * 512, text=inputs, images=[search_image_file, result_image_file], return_tensors="pt")
	inputs = {k: v.to(device) for k, v in inputs.items()}
	output_ids = model.generate(**inputs, max_new_tokens=128)
	output_ids_trimmed = [out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs['input_ids'], output_ids)]
	out_text = processor.batch_decode(output_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False)
	print(out_text)
	return float(out_text[0])

def rank_batch(model, processor, data, search_image_data=None, search_text=None):
	text_part = ""
	image_part = ""

	if search_image_data:
		search_image_file = Image.open(search_image_data)
		search_image_file.thumbnail((512, 512))
	else:
		search_image_file =None

	for i in range(0, len(data), 3):
		all_images = []
		all_prompts = []
		for r in data[i:i+3]:
			content_list = []

			result_image_file = Image.open(get_minio_image(r[1]['img_name']))
			result_image_file.thumbnail((512, 512))

			if search_image_data:
				image_part = f"- Compare [IMAGE_A] (request from user) with [IMAGE_B] (the recipe found)."

				content_list.append({"type": "text", "text": "[IMAGE_A]: "})
				content_list.append({"type": "image", "image": search_image_file})
				content_list.append({"type": "text", "text": "\n[IMAGE_B]: "})
				content_list.append({"type": "image", "image": result_image_file})
			if search_text:
				text_part = f"- Also consider the Text: \"{search_text}\" (user query) vs Founded recipe text: \"{r[1]['title']}\n{r[1]['text']}\"."
			prompt = f"""
		Goal: Culinary Similarity Evaluation.
		Task: Evaluate the relevance between the two images provided below.
		{image_part}
		{text_part}
		Criteria:
		1. Ignore the presentation/setting (e.g. cake stand vs parchment paper).
		2. Focus on: Core ingredients (chocolate, nuts, meat) and the food category.
		3. A cake and chocolate cupcake share the same core ingredients (Chocolate).

		Scale:
		- 1.0: Exact match.
		- 0.7-0.9: Both are from same category (e.g cakes, salad, pizza etc.).
		- 0.5-0.7: High similarity in core ingredients (e.g. both are chocolate-based desserts).
		- 0.0: No shared ingredients or category (e.g., Chocolate vs Salad).

		Return ONLY the score as a float with exactly two decimal places (e.g., 0.85, 0.70).
		"""
			content_list.append({"type": "text", "text": f"\n{prompt}"})
			messages = [
				{
					"role": "user",
					"content": content_list
				}
			]

			inputs = processor.apply_chat_template(
				messages,
				tokenize=False,
				add_generation_prompt=True
			)
			if search_image_data:
				all_images.append([search_image_file, result_image_file])
			all_prompts.append(inputs)
		processor.tokenizer.padding_side = "left"
		if search_image_data:
			inputs = processor(max_pixels=512*512, text=all_prompts, images=all_images, padding=True, return_tensors="pt")
		else:
			inputs = processor(max_pixels=512 * 512, text=all_prompts, padding=True, return_tensors="pt")
		inputs = {k: v.to(device) for k, v in inputs.items()}
		start_time = time.time()
		with torch.no_grad():
			output_ids = model.generate(**inputs, max_new_tokens=15, do_sample=False, use_cache=True)
		print(f"Time: {time.time() - start_time}")
		output_ids_trimmed = [out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs['input_ids'], output_ids)]
		out_text = processor.batch_decode(output_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False)
		print(out_text)

		for j, text in enumerate(out_text):
			try:
				idx = i + j
				data[idx][1]['rerank_score'] = float(text)
			except:
				print("Error in reranking")
				data[idx][1]['rerank_score'] = 0.0
		del inputs, output_ids, output_ids_trimmed
		torch.cuda.empty_cache()

	data.sort(key=lambda x: x[1]['rerank_score'], reverse=True)

def get_minio_image(image_name):
	resp = minio_client.get_object(BUCKET_NAME, image_name)
	filde_data = resp.read()

	return io.BytesIO(filde_data)

async def rerank(image_query, text_query, data):
	for r in data:
		rank_res = rank(qwen, qwen_processor,
					 search_image= image_query,
					 result_image=get_minio_image(r[1]['img_name']),
					 search_text=text_query,
					 recipe_title=r[1]['title'],
					 recipe_text=r[1]['text'])
		r[1]['rerank_score'] = rank_res

	data = sorted(data, key=lambda x: -x[1]['rerank_score'])

async def process_query(text_query: str, image_query: UploadFile, results_count, alpha, reranking=False):
	img_emb = None
	text_emb = None
	image_emb_res = []
	text_emb_res = []
	img_obj = None

	if image_query is not None and image_query.filename != "":
		try:
			file_content = await image_query.read()
			img_obj = io.BytesIO(file_content)
			img_emb = image_embedding(model, image_processor, img_obj)
			image_emb_res = search_image(img_emb, TOP_K)
		except Exception as e:
			print(e)
			raise UnsupportedTypeException("File type not supported")

	if text_query != "":
		text_emb = text_embedding(model, text_tokenizer, text_query)
		text_emb_res = search_text(text_emb, TOP_K)

	fused = late_fusion_with_norm(image_emb_res, text_emb_res, alpha=alpha, threshold=results_count)

	if reranking:

		await run_in_threadpool(rank_batch, qwen, qwen_processor, fused['result'], img_obj, text_query)

	response = []
	for data in fused["result"]:
		m = minio_client.presigned_get_object(BUCKET_NAME, data[1]['img_name'], expires=timedelta(hours=1))
		response.append(SearchResults(text=data[1]['text'], image_path=m, title=data[1]['title']))

	return response

def evaluate(alpha):
	res = []
	with open("./val_data/data.json") as f:
		data = json.load(f)

	for d in data:
		file_path = "./val_data/" + d['image_name']
		text_query = d['recipe_name']
		img_emb = image_embedding(model, processor, file_path)
		image_emb_res = search_image(img_emb, TOP_K)

		text_emb = text_embedding(model, tokenizer, text_query)
		text_emb_res = search_text(text_emb, TOP_K)

		fused = late_fusion_with_norm(image_emb_res, text_emb_res, alpha=alpha, threshold=20)

		print(fused["overlap_rate_perc"])
		res.append({"search": {"image": d['image_name'], "text": d['recipe_name']}, "result": fused})
	return res

def get_image(bucket_name, object_name):
	bucket = minio_client.bucket_exists(BUCKET_NAME)
	if not bucket:
		minio_client.make_bucket(BUCKET_NAME)
		print("bucket created")
	else:
		print("bucket exists")

	minio_client.fget_object(BUCKET_NAME, "f1.jpg", f"./tmp/{object_name}")
