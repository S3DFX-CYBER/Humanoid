"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Central configuration for the Humanoid API."""

    # Database
    database_url: str = "postgresql://humanoid:humanoid@localhost:5432/humanoid"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Rate Limits & Quotas
    max_concurrent_jobs_per_user: int = 3
    max_daily_jobs_per_user: int = 20

    # Model settings
    supabase_url: str = "http://localhost:54321"
    supabase_key: str = ""
    supabase_service_key: str = ""

    # LLM Providers
    gemini_api_key: str = ""

    # App
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    environment: str = "development"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
