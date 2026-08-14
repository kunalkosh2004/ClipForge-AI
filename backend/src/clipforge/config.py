import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "ClipForge AI"
    app_env: Literal["development", "staging", "production", "test"] = "development"
    log_level: str = "INFO"
    cors_origins: list[str] = ["*"]

    database_url: str = (
        "postgresql+asyncpg://clipforge:clipforge@localhost:5436/clipforge"
    )
    redis_url: str = "redis://localhost:6382/0"

    jwt_secret: SecretStr = SecretStr("dev-only-secret-change-me-before-any-real-deploy-1234")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

    ai_provider: Literal["gemini", "openai", "mock"] = "gemini"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-flash-latest"
    gemini_models: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "gemini-2.5-flash",
            "gemini-3.5-flash",
            "gemini-flash-lite-latest",
        ]
    )
    gemini_api_keys: Annotated[list[SecretStr], NoDecode] = Field(default_factory=list)
    gemini_daily_token_limit: int = 200_000
    gemini_daily_request_limit: int = 20

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: object) -> object:
        """Force the asyncpg driver and drop params asyncpg cannot parse.

        Hosted Postgres (Render, Neon) hand out URLs asyncpg rejects:
        postgres:// without a driver (falls back to psycopg2), and query
        params like sslmode= / channel_binding= that only libpq accepts.
        We pin the asyncpg dialect, translate sslmode -> ssl, and strip
        everything else (e.g. channel_binding) from the query string.
        """
        if not isinstance(value, str) or not value.strip():
            return value
        url = value.strip()
        if url.startswith("postgresql://") or url.startswith("postgres://"):
            url = "postgresql+asyncpg://" + url.split("://", 1)[1]
        if "?" in url:
            base, _, query = url.partition("?")
            params = [
                p
                for p in query.split("&")
                if p and not p.startswith("channel_binding=")
            ]
            params = [
                p.replace("sslmode=", "ssl=", 1) if p.startswith("sslmode=") else p
                for p in params
            ]
            url = base + ("?" + "&".join(params) if params else "")
        return url

    @field_validator("gemini_models", mode="before")
    @classmethod
    def _parse_models(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return ["gemini-2.5-flash", "gemini-3.5-flash", "gemini-flash-lite-latest"]
        if isinstance(value, str) and value.strip().startswith("["):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return [k.strip() for k in value.strip("[]").split(",") if k.strip()]
        if isinstance(value, str):
            return [k.strip() for k in value.split(",") if k.strip()]
        return value

    @field_validator("gemini_api_keys", mode="before")
    @classmethod
    def _parse_api_keys(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return []
        if isinstance(value, str) and value.strip().startswith("["):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return [k.strip() for k in value.strip("[]").split(",") if k.strip()]
        if isinstance(value, str):
            return [k.strip() for k in value.split(",") if k.strip()]
        return value

    def gemini_keys(self) -> list[SecretStr]:
        """Primary key first, then the fallback chain (deduped, empties dropped)."""
        keys: list[SecretStr] = []
        for key in [self.gemini_api_key, *self.gemini_api_keys]:
            if key is None or not key.get_secret_value().strip():
                continue
            if key not in keys:
                keys.append(key)
        return keys

    storage_backend: Literal["local", "s3"] = "local"
    storage_root: str = "./storage"
    storage_signing_secret: SecretStr = SecretStr("dev-only-storage-secret")
    public_base_url: str = "http://localhost:8000"

    # S3 storage (STORAGE_BACKEND=s3). Credentials may also come from the
    # ambient AWS environment / IAM role; explicit keys are optional.
    s3_bucket: str | None = None
    s3_region: str = "us-east-1"
    s3_endpoint_url: str | None = None
    aws_access_key_id: SecretStr | None = None
    aws_secret_access_key: SecretStr | None = None

    queue_default: str = "default"
    queue_import: str = "import"
    queue_ai: str = "ai"
    queue_render: str = "render"
    queue_media: str = "media"
    queue_dead: str = "dead"

    beat_detector: Literal["energy", "librosa"] = "energy"
    intelligence_max_attempts: int = 5

    # Caption rendering backend: "legacy" is the static ASS karaoke sweep,
    # "ass" exports MotionCaption's animated ASS, "frames" composites the
    # MotionCaption PNG frame sequence over the clip (full motion typography).
    caption_engine: Literal["legacy", "ass", "frames"] = "frames"

    otel_enabled: bool = False
    otel_service_name: str = "clipforge-api"


@lru_cache
def get_settings() -> Settings:
    return Settings()
