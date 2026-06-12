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

    def rank_batch(self, data, search_image_data=None, search_text=None):
        text_part = ""
        image_part = ""

        if search_image_data:
            search_image_file = Image.open(search_image_data)
            search_image_file.thumbnail((512, 512))
        else:
            search_image_file = None

        for i in range(0, len(data), 3):
            all_images = []
            all_prompts = []
            for r in data[i:i + 3]:
                content_list = []

                result_image_file = Image.open(self.minio_client.get_minio_image(r[1]['img_name']))
                result_image_file.thumbnail((512, 512))

                if search_image_data:
                    image_part = f"- Compare [IMAGE_A] (request from user) with [IMAGE_B] (the recipe found)."

                    content_list.append({"type": "text", "text": "[IMAGE_A]: "})
                    content_list.append({"type": "image", "image": search_image_file})
                    content_list.append({"type": "text", "text": "\n[IMAGE_B]: "})
                    content_list.append({"type": "image", "image": result_image_file})
                if search_text:
                    text_part = f"- Also consider the Text: \"{search_text}\" (user query) vs Founded recipe text: \"{r[1]['title']}\n{r[1]['text']}\"."
                prompt = f"""
            Goal: Culinary Similarity Evaluation.
            Task: Evaluate the relevance between the two images provided below.
            {image_part}
            {text_part}
            Criteria:
            1. Ignore the presentation/setting (e.g. cake stand vs parchment paper).
            2. Focus on: Core ingredients (chocolate, nuts, meat) and the food category.
            3. A cake and chocolate cupcake share the same core ingredients (Chocolate). 

            Scale:
            - 1.0: Exact match.
            - 0.7-0.9: Both are from same category (e.g cakes, salad, pizza etc.).
            - 0.5-0.7: High similarity in core ingredients (e.g. both are chocolate-based desserts).
            - 0.0: No shared ingredients or category (e.g., Chocolate vs Salad).

            Return ONLY the score as a float with exactly two decimal places (e.g., 0.85, 0.70).
            """
                content_list.append({"type": "text", "text": f"\n{prompt}"})
                messages = [
                    {
                        "role": "user",
                        "content": content_list
                    }
                ]

                inputs = self.processor.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True
                )
                if search_image_data:
                    all_images.append([search_image_file, result_image_file])
                all_prompts.append(inputs)
            self.processor.tokenizer.padding_side = "left"
            if search_image_data:
                inputs = self.processor(max_pixels=512 * 512, text=all_prompts, images=all_images, padding=True,
                                   return_tensors="pt")
            else:
                inputs = self.processor(max_pixels=512 * 512, text=all_prompts, padding=True, return_tensors="pt")
            inputs = {k: v.to(device) for k, v in inputs.items()}
            start_time = time.time()
            with torch.no_grad():
                output_ids = self.model.generate(**inputs, max_new_tokens=15, do_sample=False, use_cache=True)
            print(f"Time: {time.time() - start_time}")
            output_ids_trimmed = [out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs['input_ids'], output_ids)]
            out_text = self.processor.batch_decode(output_ids_trimmed, skip_special_tokens=True,
                                              clean_up_tokenization_spaces=False)
            print(out_text)

            for j, text in enumerate(out_text):
                try:
                    idx = i + j
                    data[idx][1]['rerank_score'] = float(text)
                except:
                    print("Error in reranking")
                    data[idx][1]['rerank_score'] = 0.0
            del inputs, output_ids, output_ids_trimmed
            torch.cuda.empty_cache()

        data.sort(key=lambda x: x[1]['rerank_score'], reverse=True)