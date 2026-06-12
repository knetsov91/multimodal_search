import io
import UnsupportedTypeException
from schemas.schemas import SearchResults
from fastapi.concurrency import run_in_threadpool

def get_min_max(results):
    if not results:
        return 0.0, 1.0
    scores = [r['distance'] for r in results]
    return min(scores), max(scores)


class TwoStageRetrieve:
    def __init__(self, retriever, search_client, minio_client, reranker = None):
        self.retriever = retriever
        self.reranker = reranker
        self.search_client = search_client
        self.minio_client = minio_client

    async def process_query(self, text_query, image_query, results_count, alpha, reranking=False):
        img_emb = None
        text_emb = None
        image_emb_res = []
        text_emb_res = []
        img_obj = None

        if image_query is not None and image_query.filename != "":
            try:
                file_content = await image_query.read()
                img_obj = io.BytesIO(file_content)
                img_emb = self.retriever.image_embedding(img_obj)
                image_emb_res = self.search_client.search_image(img_emb)
            except Exception as e:
                print(e)
                raise UnsupportedTypeException("File type not supported")

        if text_query != "":
            text_emb = self.retriever.text_embedding(text_query)
            text_emb_res = self.search_client.search_text(text_emb)

        fused = self.late_fusion_with_norm(image_emb_res, text_emb_res, alpha=alpha, threshold=results_count)

        if reranking:
            await run_in_threadpool(self.reranker.rerank,fused['result'], img_obj, text_query)

        response = []
        for data in fused["result"]:
            m = self.minio_client.generate_presigned_url(data[1]['img_name'])
            response.append(SearchResults(text=data[1]['text'], image_path=m, title=data[1]['title'], id=str(data[0])))

        return response

    def late_fusion_with_norm(self, image_list, text_list, alpha=0.5, threshold=50):

        if alpha > 1.0:
            raise Exception("Illegal alpha")
        raw_images = image_list[0] if len(image_list) > 0 else []
        raw_texts = text_list[0] if len(text_list) > 0 else []

        if len(image_list) == 0:
            alpha == 1.0
        if len(text_list) == 0:
            alpha == 0.0
        image_set = set()
        text_set = set()

        min_i, max_i = get_min_max(raw_images)
        min_t, max_t = get_min_max(raw_texts)

        fused_results = {}

        for img in raw_images:
            m_id = img['m_id']
            image_set.add(m_id)
            norm_img = (img['distance'] - min_i) / (max_i - min_i + 1e-6)  # 1e-6 против  делене на 0
            img_score = (1 - alpha) * norm_img
            fused_results[m_id] = {
                "score": img_score,
                "text": img['entity']['text'],
                "img_name": img['entity']['img_name'],
                "title": img['entity']['title']
            }

        for txt in raw_texts:
            m_id = txt['m_id']
            text_set.add(m_id)
            norm_txt = (txt['distance'] - min_t) / (max_t - min_t + 1e-6)
            txt_score = alpha * norm_txt
            if m_id in fused_results:
                fused_results[m_id]['score'] += txt_score
            else:
                fused_results[m_id] = {
                    "score": txt_score,
                    "text": txt['entity']['text'],
                    "img_name": txt['entity']['img_name'],
                    "title": txt['entity']['title']

                }

        sorted_res = sorted(fused_results.items(), key=lambda x: x[1]['score'], reverse=True)

        return {
            "result": sorted_res[:threshold]
        }
