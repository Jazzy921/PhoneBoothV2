from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    app_name: str = "Phonebooth API"
    app_env: str = "dev"
    api_prefix: str = "/api/v1"

    supabase_url: str
    supabase_db_url: str
    supabase_jwks_url: str
    supabase_jwt_audience: str = "authenticated"

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"])
    redis_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
