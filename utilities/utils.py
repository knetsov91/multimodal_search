import os
from pymilvus import MilvusClient

import config

MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
milvus_client = MilvusClient(uri=f"http://{MILVUS_HOST}:19530")
try:
    milvus_client.alter_collection_properties(collection_name=config.get_settings().collection_name,
                                              properties={"allow_insert_auto_id": "true"})
except Exception:
    pass

