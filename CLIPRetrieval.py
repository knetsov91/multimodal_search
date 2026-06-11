from BaseRetrieval import BaseRetrieval
from transformers import AutoModel, AutoImageProcessor, AutoTokenizer, Qwen3VLForConditionalGeneration, AutoProcessor
MODEL_NAME = "openai/clip-vit-base-patch16"
import torch
from PIL import Image

device = torch.device('cuda' if torch.cuda.is_available() else "cpu")
class CLIPRetrieval(BaseRetrieval):

	def __init__(self, alpha):
		super().__init__(alpha)
		self.model = AutoModel.from_pretrained(MODEL_NAME).to(device)
		self.image_processor = AutoImageProcessor.from_pretrained(MODEL_NAME)
		self.text_tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

	def text_embedding(self, text):
		inputs = self.text_tokenizer(text, truncation=True, return_tensors="pt")
		inputs = {k: v.to(device) for k, v in inputs.items()}
		with torch.no_grad():
			output = self.model.get_text_features(**inputs)
			output = output.pooler_output
		return output

	def image_embedding(self, image):
		inputs = self.image_processor([Image.open(image)], return_tensors="pt")
		inputs["pixel_values"] = inputs['pixel_values'].to(device)
		with torch.no_grad():
			img_emb = self.model.get_image_features(**inputs)
			img_emb = img_emb.pooler_output
		return img_emb
