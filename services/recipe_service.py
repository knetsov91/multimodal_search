import base64
import io
from schemas.schemas import SearchResults
import torch.nn.functional as F
from config import get_settings
from tasks.recipe_tasks import process_recipe
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
		try:
			file_b64 = None
			filename = None
			content_type = None
			if file and file.filename != "":
				file_content = await file.read()
				file_b64 = base64.b64encode(file_content).decode()
				filename = file.filename
				content_type = file.content_type

			process_recipe.delay(
				file_b64=file_b64,
				filename=filename,
				content_type=content_type,
				title=title,
				text=text,
				recipe_id=id,
			)

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
