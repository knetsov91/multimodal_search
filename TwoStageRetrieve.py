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
