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

