from pydantic import BaseModel, EmailStr
from typing import List, Generic, TypeVar, Optional

class TextQuery(BaseModel):
	text: str
class RegisterForm(BaseModel):
	email: EmailStr
	password: str
class LoginForm(BaseModel):
	email: str
	password: str

class SearchResults(BaseModel):
	text: str
	image_path: str
	title: str
	id: str
	is_admin: bool = False

T = TypeVar("T")
class PaginatedSearchResults(BaseModel, Generic[T]):
	total: int
	limit: int
	offset: int
	data: List[SearchResults]

class SettingsChange(BaseModel):
	alpha: Optional[float] = None
	pagination_size: Optional[int] = None
	retrieval_size: Optional[int] = None
	reranking: Optional[bool] = False
