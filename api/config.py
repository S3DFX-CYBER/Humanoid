"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the Humanoid API."""

    # Database
    database_url: str = "postgresql://humanoid_app:humanoid_app@localhost:5432/humanoid"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Rate Limits & Quotas
    max_concurrent_jobs_per_user: int = 3
    max_daily_jobs_per_user: int = 20
    max_topic_chars: int = 500

    # Supabase
    supabase_url: str = "http://localhost:54321"
    supabase_key: str = ""
    supabase_service_key: str = ""

    # LLM Providers
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-004"
    embedding_dimensions: int = 384
    # Only enable in development: a stub provider never produces usable prose.
    allow_stub_provider: bool = False

    # Internal services
    render_service_url: str = "http://render:8002"
    render_timeout_seconds: float = 120.0
    ingestion_service_url: str = "http://ingestion:8001"

    # CORS — comma separated list
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # Development-only auth bypass. Never set this in production.
    dev_auth_user_id: str = ""
    dev_auth_user_email: str = "dev@humanoid.local"

    # App
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    environment: str = "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def dev_auth_enabled(self) -> bool:
        """Dev auth bypass is only ever honoured outside production."""
        return bool(self.dev_auth_user_id) and not self.is_production


@lru_cache
def get_settings() -> Settings:
    return Settings()
