from schemas.schemas import SearchResults
import torch.nn.functional as F
import  io
from config import get_settings
class RecipeService:
	def __init__(self, retrieve_model, milvus_client, minio_client):
		self.retrieve_model = retrieve_model
		self.milvus_client = milvus_client
		self.minio_client = minio_client
		self.settings = get_settings()

	def get_recipes(self, offset=0, limit=10):
		total_count = self.milvus_client.get_collection_stats(self.settings.collection_name)["row_count"]
		res = self.milvus_client.query(
			collection_name=self.settings.collection_name,
			filter="",  # Empty filter matches all entities
			output_fields=["*"],
			limit=limit,
			offset=offset# Return all fields
		)
		data = []
		for r in res:
			data.append(SearchResults(
									title=r['title'], text=r['text'],
									image_path=self.minio_client.generate_presigned_url(r['img_name']),
									id=str(r['m_id']))
			)
		return {
			"total": total_count,
			"data": data,
			"limit": limit,
			"offset": offset
		}

	async def save_recipe(self, file , title, text, id = None):
		if text == None or len(text) == 0:
			raise Exception("Text is required")
		if title == None or len(title) == 0:
			raise Exception("Title is required")
		text_emb = self.retrieve_model.text_embedding(text)
		text_emb_norm = F.normalize(text_emb, p=2, dim=-1)

		data = {
			"text": text,
			"text_emb": text_emb_norm.tolist()[0],
			"title": title
		}
		try:
			if id:
				data["m_id"] = id
				old = self.get_recipe_by_id(id)[0]
				if old:
					if "img_name" in old:
						data["img_name"] = old["img_name"]
					if "img_emb" in old:
						data["img_emb"] = old["img_emb"]

			if file and file.filename != "":
				file_content = await file.read()
				file_size = len(file_content)
				file_buffer = io.BytesIO(file_content)
				img_emb = self.retrieve_model.image_embedding(file_buffer)
				img_emb_norm = F.normalize(img_emb, p=2, dim=-1)
				data["img_emb"] = img_emb_norm.tolist()[0]
				data["img_name"] = file.filename
				await self.minio_client.upload_file(file)


			if id:
				self.milvus_client.upsert(collection_name=self.settings.collection_name,data=data)
			else:
				self.milvus_client.insert(collection_name=self.settings.collection_name,data=data)

		except Exception as e:
		   raise Exception(e)
	def get_recipe_by_id(self, id):
		recipe=self.milvus_client.get(collection_name=self.settings.collection_name,
									  ids=[id], output_fields=["img_name", "title", "text", "img_emb"])

		return recipe
	def insert_recipe(self, data):
		self.milvus_client.insert(
			collection_name=self.settings.collection_name,
			data=data
		)

	def delete_recipe(self, id):
		self.milvus_client.delete(collection_name=self.settings.collection_name, ids=[id])
