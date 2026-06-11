from fastapi import APIRouter,Request
from fastapi.responses import RedirectResponse
from fastapi import Form, Depends
from sqlalchemy.orm import Session
from db.database import get_db
from fastapi.templating import Jinja2Templates
from services.user_service import register, login
from schemas.schemas import RegisterForm, LoginForm
from pydantic import ValidationError

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/login")
def login_view(request: Request):
	user = request.session.get("user")
	if user:
		return RedirectResponse(url="/", status_code=303)
	return templates.TemplateResponse(name="login.html", request=request, context={"session": request.session})

@router.post("/login")
def login_post(
		request: Request,
		data: LoginForm = Form(),
		db: Session = Depends(get_db)
):

	if data.email == "admin" and data.password == "admin":
		request.session["user"] = {"email": "admin", "role": "admin"}
		return RedirectResponse(url="/admin", status_code=303)
	try:
		u = login(db, data.email, data.password)
		resp = RedirectResponse(url="/", status_code=302)
		request.session["user"] = {"email": u.email, "role": u.role}
		resp.set_cookie(key="sess", value="token")

		return resp
	except Exception as e:
		return templates.TemplateResponse(name="login.html", request=request, context={"session": request.session,
																					   "error": "Something went wrong. Try again."})

@router.get("/register")
def register_view(request: Request):
	return templates.TemplateResponse(name="register.html", request=request, context={"session": request.session})

@router.post("/register")
async def signup(request: Request,
			 db: Session = Depends(get_db)):
	errors = {}
	form_data = await request.form()
	try:
		reg_data = RegisterForm(**form_data)
	except ValidationError as e:
		print(e.errors())
		errors["email"] = e.errors()[0]['msg'].split(":")[1]

	password = form_data.get("password", "")
	email = form_data.get("email", "")
	if not password or password == "" or len(password) < 6:
		errors["password"] = "Password have to be at least 6 symbols"
	if len(errors.keys()) > 0:
		return templates.TemplateResponse(name="register.html", request=request, context={"session": request.session, "errors": errors})
	try:
		register(db, email, password)
	except Exception as e:
		return templates.TemplateResponse(name="register.html", request=request, context={"session": request.session, "error": "There is error"})
	return RedirectResponse(url="/login", status_code=303)

@router.get("/logout")
def logout(request: Request):
	request.session.clear()
	return RedirectResponse(url="/", status_code=303)
