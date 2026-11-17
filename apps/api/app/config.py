from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    clip_env: str = "development"
    database_url: str = "postgresql+psycopg://clip:clip@localhost:5432/clipstudio"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "dev-only-change-me"
    jwt_ttl_seconds: int = 60 * 60 * 24 * 14
    cookie_name: str = "clip_session"
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    allow_signup: bool = True
    cors_origins: str = "http://localhost:3000"

    s3_endpoint: str = "http://localhost:9000"
    s3_public_endpoint: str = ""
    s3_access_key_id: str = "clip"
    s3_secret_access_key: str = "clipsecret"
    s3_bucket: str = "clip-studio"
    s3_region: str = "us-east-1"

    max_video_duration_seconds: int = 7200
    max_upload_bytes: int = 500 * 1024 * 1024
    worker_concurrency: int = 1
    cleanup_interval_seconds: int = 3600
    cleanup_max_age_seconds: int = 6 * 3600

    transcribe_provider: str = "groq"
    transcribe_language: str = ""
    transcribe_max_bytes: int = 20_000_000
    groq_api_key: str = ""
    groq_whisper_model: str = "whisper-large-v3-turbo"
    openai_api_key: str = ""
    openai_whisper_model: str = "whisper-1"
    faster_whisper_model: str = "small"
    local_chunk_seconds: int = 600

    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-4-5"
    anthropic_api_key: str = ""

    postiz_url: str = ""
    postiz_api_key: str = ""

    @field_validator("cookie_samesite")
    @classmethod
    def validate_samesite(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"lax", "strict", "none"}:
            raise ValueError("COOKIE_SAMESITE deve ser lax, strict ou none")
        return normalized

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]
        if url.startswith("postgresql://"):
            return "postgresql+psycopg://" + url[len("postgresql://") :]
        return url

    def ensure_production_secrets(self) -> None:
        if self.clip_env != "production":
            return
        if self.jwt_secret == "dev-only-change-me":
            raise RuntimeError("Defina JWT_SECRET em produção")


@lru_cache
def get_settings() -> Settings:
    return Settings()
