from utillities import (MilvusClient, milvus_client, COLLECTION_NAME,
                        DataType, text_tokenizer, image_processor, device,
                        DATASET_PATH, model as clip_model, minio_client,
                        BUCKET_NAME)

from PIL import Image
import re
import json
import pandas as pd
from fastapi import File, UploadFile
import io
import torch.nn.functional as F
from utillities import text_embedding, image_embedding, model

MINIO_HOST="localhost:9000"
TRAIN_IMAGES_PATH="/home/kosio/.cache/kagglehub/datasets/jeromeblanchet/recipeqa-nlp-dataset/versions/1/images/images-qa/train/images-qa"

def init_schema(client):
    schema = MilvusClient.create_schema(
        auto_id=True
    )
    index_params = MilvusClient.prepare_index_params()

    index_params.add_index(
        field_name="text_emb",
        index_type="AUTOINDEX",
        metric_type="COSINE"
    )
    index_params.add_index(
        field_name="img_emb",
        index_type="AUTOINDEX",
        metric_type="COSINE"
    )

    schema.add_field(field_name="m_id", datatype=DataType.INT64, is_primary=True)
    schema.add_field(field_name="img_name", datatype=DataType.VARCHAR, max_length=256)
    schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=65024)
    schema.add_field(field_name="img_emb", datatype=DataType.FLOAT_VECTOR, dim=512)
    schema.add_field(field_name="text_emb", datatype=DataType.FLOAT_VECTOR, dim=512)
    schema.add_field(field_name="title", datatype=DataType.VARCHAR, max_length=100)

    schema.verify()

    print(schema)
    client.create_collection(collection_name=COLLECTION_NAME, schema=schema, index_params=index_params)

def select_image(list_imgs, show=False):
    count = {}
    try:
        for img_name in list_imgs:

            img_name_splitted = re.split("_", img_name)
            # if not isnumeric(()img_name_splitted[1:][0]):
            #     raise Exception(f"Problem with image: {}")
            if img_name_splitted[0] not in count:
                count[img_name_splitted[0]] = 1
            else:
                count[img_name_splitted[0]] += 1
        el = sorted(count.items(), key=lambda x: x[1])[1][0]
        filtered = [x for x in list_imgs if x.startswith(el) and x[x.index("_") + 1].isnumeric()]
        last_img = sorted(filtered, key=lambda x: -int(re.split("_", x)[1:][0]))[0]
    except Exception as err:
        raise Exception(f"Problem with images: ")

    if show:
        print(last_img)

    return last_img

def list_to_text(lst):
    text= list(map( lambda x: x["body"], lst))
    return " ".join(text)

def prepare_index_data(ds, model, show=False):
  data = []
  recipe_ids = set()
  for d in ds:
    if d['recipe_id'] in recipe_ids:
        continue

    try:
      last_img = select_image(d['choice_list'])
      image_path = f"{TRAIN_IMAGES_PATH}/{last_img}"
      txt = list_to_text(d['context'])

      image_inputs = image_processor([Image.open(image_path)], return_tensors="pt")
      image_inputs['pixel_values'] = image_inputs['pixel_values'].to(device)
      img_output = model.get_image_features(**image_inputs) #.detach().cpu()
      img_embs = img_output.pooler_output

      text_inputs = text_tokenizer(txt, truncation=True, return_tensors="pt")
      text_inputs = {k: v.to(device) for k, v in text_inputs.items()}
      text_output = model.get_text_features(**text_inputs)#.detach().cpu()
      text_embs = text_output.pooler_output
      img_emb_norm = F.normalize(img_embs, p=2, dim=-1)
      text_emb_norm = F.normalize(text_embs, p=2, dim=-1)

      image_name = image_path.split("/")[-1]
      data.append({
          "img_name": image_name,
          "text": txt,
          "img_emb": img_emb_norm.tolist()[0],
          "text_emb": text_emb_norm.tolist()[0],
          "title": process_title(d['recipe_id'])
      })
      recipe_ids.add(d['recipe_id'])
    except Exception as e:
      print(e)
      print(f"Problem with recipe: {d['recipe_id']}, will be skiped")
      continue

    if show:
      print(data)

  return data

def insert(client, data):
	client.insert(
		collection_name=COLLECTION_NAME, data=data)

def process_title(title):
  r = " ".join(title.split("-"))
  return r.capitalize()

async def save_recipe(model, file: UploadFile(...), title, text):

    if text == None or len(text) == 0:
        raise Exception("text is empty")
    if title == None or len(title) == 0:
        raise Exception("title is empty")

    file_content = await file.read()
    file_size = len(file_content)
    file_buffer = io.BytesIO(file_content)

    text_emb = text_embedding(model, text_tokenizer, text)
    img_emb = image_embedding(model, image_processor, file_buffer)

    img_emb_norm = F.normalize(img_emb, p=2, dim=-1)
    text_emb_norm = F.normalize(text_emb, p=2, dim=-1)
    data = {
        "img_name": file.filename,
        "text": text,
        "img_emb": img_emb_norm.tolist()[0],
        "text_emb": text_emb_norm.tolist()[0],
        "title": title
    }
    try:
        insert(milvus_client, data)
        await upload_file(file)
    except Exception as e:
       raise Exception(e)

def upload_image(bucket_name, object_name, file_path):
	bucket = minio_client.bucket_exists(BUCKET_NAME)
	if not bucket:
		minio_client.make_bucket(BUCKET_NAME)
		print("bucket created")
	else:
		print("bucket exists")

	# minio_client.fput_object(BUCKET_NAME, "f1.jpg", "./iceberg.jpg",)

	# minio_client.fget_object(BUCKET_NAME, "f1.jpg", file_path)
	minio_client.fput_object(BUCKET_NAME, object_name, file_path)


def minio_upload_images(file_path=None):
    if file_path:
        with open(file_path) as j:
            prep_data = json.load(j)

    else:
        dataset = pd.read_json(DATASET_PATH + "/train recipeqa.json")["data"]
        print(len(dataset))
        prep_data = prepare_index_data(dataset[:500], clip_model)
        insert(milvus_client, prep_data)
    for d in prep_data:
        f_path = TRAIN_IMAGES_PATH + "/" + d['img_name']
        print(f_path)
        upload_image(BUCKET_NAME, d['img_name'], f_path)
# init_schema(milvus_client)
