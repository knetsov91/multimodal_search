# Multimodal Recipe Search

A multimodal search engine for recipes, supporting text queries, image queries, or both combined.

## Overview

The system uses a two-stage retrieval pipeline. In the first stage, CLIP encodes the query and retrieves the closest matches from a Milvus vector index using late fusion of text and image similarity scores. In the second stage (optional), a vision-language model reranks the top results by visually comparing each candidate against the original query.

**Stack:**
- FastAPI + Uvicorn
- Milvus (vector search)
- MinIO (image storage)
- PostgreSQL (user/recipe metadata)
- CLIP ViT-B/16 (retrieval)
- Qwen3-VL-4B-Instruct 4-bit NF4 (reranking)
- Jinja2 templates (frontend)
