from fastapi import APIRouter, Request
from schemas.schemas import SearchResults
from typing import List, Optional
from fastapi import File, UploadFile, HTTPException, Form, Depends
from TwoStageRetrieve import TwoStageRetrieve
from CLIPRetrieval import CLIPRetrieval
from QwenReranker import QwenReranker
from MinioStorageClient import MinioStorageClient
from MilvusSearch import MilvusSearch
from transformers import BitsAndBytesConfig, Qwen3VLForConditionalGeneration, AutoProcessor
import torch
from config import get_settings, Settings
from UnsupportedTypeException import UnsupportedTypeException
from services.recipe_service import RecipeService
from utils import process_query
import os
import logging
from pymilvus import MilvusClient

logger = logging.getLogger(__name__)

settings = get_settings()

qwen = None
qwen_processor = None
if settings.reranking:
	config = BitsAndBytesConfig(load_in_4bit=True,
								bnb_4bit_compute_dtype=torch.bfloat16,
								bnb_4bit_quant_type="nf4",
								bnb_4bit_use_double_quant=True)

	qwen = Qwen3VLForConditionalGeneration.from_pretrained("Qwen/Qwen3-VL-4B-Instruct",
														   torch_dtype=torch.float16,
														   device_map="auto",
														   quantization_config=config,
														   attn_implementation="sdpa",
														   low_cpu_mem_usage=True,
														  )
														   #local_files_only=True)

	qwen_processor =  AutoProcessor.from_pretrained("Qwen/Qwen3-VL-4B-Instruct", max_pixels=128*28*28)

MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
BUCKET_NAME="images"
COLLECTION_NAME="cooking_3000"

retrieval = CLIPRetrieval(alpha=0.5)
milvus_client = MilvusClient(uri=f"http://{MILVUS_HOST}:19530")
minio_client_v2 = MinioStorageClient(bucket_name=settings.bucket_name)
milvus_client_v2 = MilvusSearch(milvus_client=milvus_client, collection_name=settings.collection_name, k=20)
reranker = QwenReranker(model=qwen, processor=qwen_processor, minio_client=minio_client_v2)
# reranker.load_model()

two_stage_retrieve = TwoStageRetrieve(retriever=retrieval,
									  search_client=milvus_client_v2,
									  reranker=reranker,
									  minio_client=minio_client_v2)
recipe_service = RecipeService(
							retrieve_model=retrieval,
	milvus_client=milvus_client,
	minio_client=minio_client_v2
							)

router = APIRouter(prefix="/api")

@router.post("/v1/search", response_model=List[SearchResults])
async def search(
	image_query: Optional[UploadFile] = File(None),
	text_query: Optional[str] = Form(""),
	count: Optional[int] = Form(None),
	alpha: Optional[float] = Form(None),
	rerank: Optional[bool] = Form(False),
	settings: Settings = Depends(get_settings)
):
	if text_query == "" and  (image_query is None or image_query.filename == ""):
		raise HTTPException(status_code=400, detail="Please provide text,image or both")
	result = []
	final_alpha = alpha if alpha else settings.alpha
	fetch_size = count if count else settings.retrieval_size
	logger.info("v1 search request", extra={"text_query": text_query, "alpha": final_alpha, "fetch_size": fetch_size, "rerank": rerank})
	try:
		result = await process_query(text_query, image_query, fetch_size, final_alpha, reranking=rerank)
		if not result:
			logger.warning("v1 search returned no results", extra={"text_query": text_query, "alpha": final_alpha})
	except Exception as e:
		logger.exception(
			"v1 search failed",
			extra={"text_query": text_query, "alpha": final_alpha, "fetch_size": fetch_size, "rerank": rerank}
		)
		if type(e) == UnsupportedTypeException:
			raise HTTPException(status_code=400, detail=str(e))
		raise HTTPException(status_code=400, detail="Something went wrong")

	return result

@router.post("/v2/search", response_model=List[SearchResults])
async def search_v2(
	request: Request,
	image_query: Optional[UploadFile] = File(None),
	text_query: Optional[str] = Form(""),
	count: Optional[int] = Form(None),
	alpha: Optional[float] = Form(None),
	rerank: Optional[bool] = Form(False),
	settings: Settings = Depends(get_settings),

):
	user = request.session.get("user")

	if text_query == "" and  (image_query is None or image_query.filename == ""):
		raise HTTPException(status_code=400, detail="Please provide text,image or both")
	result = []
	final_alpha = alpha if alpha else settings.alpha
	fetch_size = count if count else settings.retrieval_size
	try:
		result = await two_stage_retrieve.process_query(text_query, image_query, fetch_size, final_alpha, reranking=rerank)
		if user and user["role"] == "admin":
			for i in range(len(result)):
				result[i].is_admin =True
	except Exception as e:
		logger.exception(
			"v2 search failed",
			extra={"text_query": text_query, "alpha": final_alpha, "fetch_size": fetch_size, "rerank": rerank, "user": user}
		)
		if type(e) == UnsupportedTypeException:
			raise HTTPException(status_code=400, detail=str(e))
		raise HTTPException(status_code=400, detail="Something went wrong")

	return result
