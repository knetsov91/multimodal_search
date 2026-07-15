import base64
import io
import torch.nn.functional as F
from celery_app import celery_app
from CLIPRetrieval import CLIPRetrieval
from MinioStorageClient import MinioStorageClient
from utilities import utils
from config import get_settings
from db.database import SessionLocal
from models.models import Recipe

settings = get_settings()

_retrieval = None
_minio_client = None


def _get_retrieval():
    global _retrieval
    if _retrieval is None:
        _retrieval = CLIPRetrieval(alpha=0.5)
    return _retrieval


def _get_minio():
    global _minio_client
    if _minio_client is None:
        _minio_client = MinioStorageClient(bucket_name=settings.bucket_name)
    return _minio_client


def _process_one(retrieval, minio, file_b64, filename, content_type, title, text, recipe_id=None):
    if not text:
        raise ValueError("Text is required")
    if not title:
        raise ValueError("Title is required")

    text_emb = retrieval.text_embedding(text)
    text_emb_norm = F.normalize(text_emb, p=2, dim=-1)

    data = {
        "text": text,
        "text_emb": text_emb_norm.tolist()[0],
        "title": title,
        "img_name": "",
        "img_emb": [0.0] * 512,
    }

    if recipe_id:
        data["m_id"] = recipe_id
        existing = utils.milvus_client.get(
            collection_name=settings.collection_name,
            ids=[recipe_id],
            output_fields=["img_name", "img_emb"],
        )
        if existing:
            if "img_name" in existing[0]:
                data["img_name"] = existing[0]["img_name"]
            if "img_emb" in existing[0]:
                data["img_emb"] = existing[0]["img_emb"]

    if file_b64 and filename:
        file_bytes = base64.b64decode(file_b64)
        file_buffer = io.BytesIO(file_bytes)
        img_emb = retrieval.image_embedding(file_buffer)
        img_emb_norm = F.normalize(img_emb, p=2, dim=-1)
        data["img_emb"] = img_emb_norm.tolist()[0]
        data["img_name"] = filename
        minio.upload_bytes(file_bytes, filename, content_type or "application/octet-stream")

    if recipe_id:
        utils.milvus_client.upsert(collection_name=settings.collection_name, data=data)
    else:
        utils.milvus_client.insert(collection_name=settings.collection_name, data=data)


@celery_app.task(bind=True, name="tasks.process_recipe")
def process_recipe(self, file_b64, filename, content_type, title, text, recipe_id=None):
    _process_one(
        _get_retrieval(), _get_minio(),
        file_b64, filename, content_type, title, text, recipe_id,
    )
    return {"status": "complete", "title": title}


@celery_app.task(bind=True, name="tasks.process_bulk_recipes")
def process_bulk_recipes(self, recipes):
    retrieval = _get_retrieval()
    minio = _get_minio()
    total = len(recipes)
    results = []

    for i, recipe in enumerate(recipes):
        self.update_state(
            state="PROGRESS",
            meta={"current": i, "total": total, "title": recipe["title"]},
        )
        try:
            _process_one(
                retrieval,
                minio,
                recipe.get("file_b64"),
                recipe.get("filename"),
                recipe.get("content_type"),
                recipe["title"],
                recipe["text"],
                recipe.get("recipe_id"),
            )
            results.append({"title": recipe["title"], "status": "success"})
        except Exception as exc:
            results.append({"title": recipe["title"], "status": "failed", "error": str(exc)})

    return {"status": "complete", "total": total, "results": results}
