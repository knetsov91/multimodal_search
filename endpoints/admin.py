import os
from fastapi import Request, APIRouter,Depends, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from config import Settings, get_settings
from dotenv import load_dotenv, set_key
from schemas.schemas import SettingsChange
templates = Jinja2Templates(directory="templates")
router = APIRouter()

@router.get("/admin")
async def admin(request: Request, settings: Settings = Depends(get_settings)):
	user = request.session.get("user")
	if not user or user["role"] != "admin":
		return RedirectResponse(url="/", status_code=303)
	print("admin")
	return templates.TemplateResponse(name="admin-panel.html",
                                      request=request,
                                      context={
                                            "session": request.session,
                                            "settings": settings,
                                      }
                                      )

@router.patch("/api/v1/settings")
async def update(new_settings: SettingsChange,
                 settings: Settings = Depends(get_settings)):
    settings_params = new_settings.model_dump(exclude_unset=True)
    for key,value in settings_params.items():

        if not hasattr(settings, key.lower()):
            raise HTTPException(status_code=400, detail="Invalid settings key")

        setattr(settings, key.lower(), value)
        set_key("config.env",key.upper(), value, quote_mode="never")
        os.environ[key.lower()] = str(value)
        load_dotenv("config.env", override=True)
        get_settings.cache_clear()
    return ""
