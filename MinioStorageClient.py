import os
from minio import Minio
from datetime import timedelta
import io

MINIO_HOST=os.getenv("MINIO_HOST", "localhost")

class MinioStorageClient:
    def __init__(self, bucket_name):
        self.minio_client = Minio(f"{MINIO_HOST}:9000", access_key="minioadmin", secret_key="minioadmin", secure=False)
        self.bucket_name = bucket_name

    def generate_presigned_url(self, data):
        return self.minio_client.presigned_get_object(self.bucket_name, data, expires=timedelta(hours=1))
