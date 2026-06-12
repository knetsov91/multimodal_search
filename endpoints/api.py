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
from pymilvus import MilvusClient

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
settings = get_settings()
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

