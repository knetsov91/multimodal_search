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
	def get_recipe_by_id(self, id):
		recipe=self.milvus_client.get(collection_name=self.settings.collection_name,
									  ids=[id], output_fields=["img_name", "title", "text", "img_emb"])

		return recipe