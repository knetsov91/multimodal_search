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

    def get_minio_image(self, image_name):
        resp = self.minio_client.get_object(self.bucket_name, image_name)
        file_data = resp.read()

        return io.BytesIO(file_data)

    def delete_object(self, filename: str):
        self.minio_client.remove_object(self.bucket_name, filename)

    def upload_bytes(self, file_bytes: bytes, filename: str, content_type: str = "application/octet-stream"):
        self.minio_client.put_object(
            bucket_name=self.bucket_name,
            object_name=filename,
            data=io.BytesIO(file_bytes),
            length=len(file_bytes),
            content_type=content_type,
        )

    async def upload_file(self, file):
        await file.seek(0)
        file_content = await file.read()
        file_size = len(file_content)
        file_buffer = io.BytesIO(file_content)

        self.minio_client.put_object(bucket_name=self.bucket_name,
                                object_name=file.filename,
                                data=file_buffer,
                                length=file_size,
                                content_type=file.content_type)