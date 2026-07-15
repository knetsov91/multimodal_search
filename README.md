# Multimodal Recipe Search

A multimodal search engine for recipes, supporting text queries, image queries, or both combined.

## Overview

The system uses a two-stage retrieval pipeline. In the first stage, CLIP encodes the query and retrieves the closest matches from a Milvus vector index using late fusion of text and image similarity scores. In the second stage (optional), a vision-language model reranks the top results by visually comparing each candidate against the original query.

## Configuration

There are two config files:

- `config.env` — runtime settings read by the app via pydantic-settings
- `.env` — secrets used by Docker Compose (Postgres and MinIO credentials)

`config.env`:

- `ALPHA=0.8` — weight between image and text scores in late fusion (0.0 = image only, 1.0 = text only)
- `RETRIEVAL_SIZE=6` — number of results returned per search
- `PAGINATION_SIZE=10` — page size for the recipe list view
- `RERANKING=False` — set to `True` to enable Qwen reranking (off by default)
- `BUCKET_NAME=images` — MinIO bucket where recipe images are stored
- `COLLECTION_NAME=cooking_3000` — Milvus collection name

`.env`:

- `POSTGRES_USERNAME=<postgres-username>`
- `POSTGRES_PASSWORD=<postgres-password>`
- `MINIO_USER=<minio-user>`
- `MINIO_PASSWORD=<minio-password>`
- `DOCKER_VOLUME_DIRECTORY=/path/to/volumes`

Service hostnames (`MILVUS_HOST`, `MINIO_HOST`, `POSTGRES_HOST`) default to `localhost` and can be overridden for Docker deployments.

**Stack:**
- FastAPI + Uvicorn
- Milvus (vector search, recipe title/text/embeddings)
- MinIO (image storage)
- PostgreSQL (user accounts, Celery task results)
- CLIP ViT-B/16 (retrieval)
- Qwen3-VL-4B-Instruct 4-bit NF4 (reranking)
- Jinja2 templates (frontend)

## Async processing

Recipe uploads and edits are handled by a Celery worker instead of inline in the request handler. The **/api/v1/recipes** endpoints enqueue a **process_recipe** task and return immediately; the worker generates the CLIP embeddings, uploads the image to MinIO and writes to Milvus in the background. RabbitMQ is the broker and PostgreSQL stores task results and progress. Flower gives a UI for monitoring task status.

**start.sh** launches both the Celery worker and the Uvicorn server in the container.

## Demos

Playwright scripts that run the app in a browser and record the session as a gif. The app must be running at `http://localhost:8081` first.

- **demo/search_demo.py** — text search, image search and combined text+image search, scrolling through results each time. Saves **assets/text_image_combined_search.gif**.

![Search demo](assets/text_image_combined_search.gif)
