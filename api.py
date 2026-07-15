from fastapi import FastAPI, Depends
from fastapi.responses import RedirectResponse
from endpoints import api, auth, admin, recipes
from db.database import engine, Base
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from fastapi.templating import Jinja2Templates
from fastapi import Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from config import get_settings, Settings
import sentry_sdk
import os

sentry_sdk.init(dsn=os.getenv("SENTRY_DSN", ""), enable_logs=True)

templates = Jinja2Templates(directory="templates")
app = FastAPI(title="upload services")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(api.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(recipes.router)
Base.metadata.create_all(bind=engine)

model = None

app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"]
)
app.add_middleware(SessionMiddleware, secret_key="secret")

@app.get("/info")
def get_info(settings: Settings = Depends(get_settings)):
	return {
		"alpha": settings.alpha,
		"pagination_size": settings.pagination_size,
		"retrieval_size": settings.retrieval_size
	}

@app.get("/recipes")
async def render_recipes(
		request: Request
):
	user = request.session.get("user")
	if not user or user["role"] != "admin":
		return RedirectResponse(url="/", status_code=303)
	return templates.TemplateResponse(name="recipes.html", request=request, context={"session": request.session})

@app.get("/")
async def home(request: Request, settings = Depends(get_settings)):
	print("home")
	return templates.TemplateResponse(name="index.html",
									  request=request,
									  context={"user_role": "admin",
											   "session": request.session,
											   "settings": settings}
									  )



if __name__ == "__main__":
	uvicorn.run(app, host="0.0.0.0", port=8081, reload=True)