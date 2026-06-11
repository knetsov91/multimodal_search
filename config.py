from pydantic_settings import  BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    alpha: float = 0.5
    pagination_size: int = 10
    retrieval_size: int = 5
    reranking: bool = False
    bucket_name: str
    collection_name: str
    model_config = SettingsConfigDict(env_file="config.env")

@lru_cache
def get_settings():
    return Settings()