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
