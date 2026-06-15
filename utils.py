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

