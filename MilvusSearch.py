import torch.nn.functional as F
import os
from pymilvus import MilvusClient
MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")

class MilvusSearch:
    def __init__(self, milvus_client, collection_name, k):
        self.milvus_client = milvus_client
        self.collection_name = collection_name
        self.k = k

    def search_text(self, txt_emb):
        txt_emb_norm = F.normalize(txt_emb.cpu(), p=2, dim=-1).numpy().tolist()
        r = self.milvus_client.search(
            collection_name=self.collection_name,
            anns_field="text_emb",
            data=txt_emb_norm,
            limit=self.k,
            output_fields=["m_id", "text", "img_name", "title"]
        )

        return r
