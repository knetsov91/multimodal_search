from BaseReranker import BaseReranker
import torch
from transformers import Qwen3VLForConditionalGeneration, AutoProcessor
from PIL import Image
import time

device = torch.device('cuda' if torch.cuda.is_available() else "cpu")

class QwenReranker(BaseReranker):
    def __init__(self, model, processor, minio_client ):
        self.model = model
        self.processor = processor
        self.minio_client = minio_client
    def load_model(self):
        model = Qwen3VLForConditionalGeneration.from_pretrained(MLLM_MODEL,
                                                                     dtype=torch.bfloat16,
                                                                     device_map="auto",
                                                                     quantization_config=self.config,
                                                                     attn_implementation="sdpa",
                                                                     low_cpu_mem_usage=True)
        self.model = model

        # local_files_only=True)
        self.processor = AutoProcessor.from_pretrained("Qwen/Qwen3-VL-4B-Instruct")
    def rerank(self, results, search_image_data, search_text):
        self.rank_batch( results, search_image_data, search_text)
