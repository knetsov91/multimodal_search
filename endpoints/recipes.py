from fastapi import APIRouter, Request, File, UploadFile, Response, Form, HTTPException, Query, Depends
from fastapi.responses import RedirectResponse
from typing import Optional
from fastapi.templating import Jinja2Templates
from services.recipe_service import RecipeService
from MinioStorageClient import MinioStorageClient
from MilvusSearch import MilvusSearch
from CLIPRetrieval import CLIPRetrieval
from utillities import utils
from schemas.schemas import SearchResults, PaginatedSearchResults
from config import Settings, get_settings

templates = Jinja2Templates(directory="templates")
router = APIRouter()
settings = get_settings()
retrieval = CLIPRetrieval(alpha=0.5)

minio_client_v2 = MinioStorageClient(bucket_name=settings.bucket_name)
milvus_client_v2 = MilvusSearch(collection_name=settings.collection_name, k=20, milvus_client=utils.milvus_client)
recipe_service = RecipeService(retrieve_model=retrieval,
                               minio_client=minio_client_v2,
                               milvus_client=utils.milvus_client)

@router.get("/recipe-add")
def recipe_add(request: Request):
	user = request.session.get("user")
	if not user :
		return RedirectResponse(url="/", status_code=303)
	return templates.TemplateResponse(name="recipe-add.html", request=request, context={"session": request.session})

@router.get("/recipe-edit/{id}")
def recipe_edit(request: Request,
				id: int):
	user = request.session.get("user")
	if not user or user['role'] != "admin":
		return RedirectResponse(url="/", status_code=303)
	recipe = recipe_service.get_recipe_by_id(id=id)
	img = minio_client_v2.generate_presigned_url(recipe[0]["img_name"])
	return templates.TemplateResponse(name="recipe-edit.html", request=request, context={"session": request.session, "recipe": recipe[0], "img": img, "id": id})
