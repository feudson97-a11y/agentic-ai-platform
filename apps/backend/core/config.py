"""
Enterprise Agentic AI Platform — Core Configuration
Centralized settings with environment-based overrides and validation.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Application ──────────────────────────────────────────────────────────
    APP_NAME: str = "Agentic AI Platform"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ── API ───────────────────────────────────────────────────────────────────
    API_PREFIX: str = "/api/v1"
    ALLOWED_ORIGINS: list[AnyHttpUrl] = []

    # ── Security ──────────────────────────────────────────────────────────────
    SECRET_KEY: str = Field(..., min_length=32)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ── Anthropic / Claude ────────────────────────────────────────────────────
    ANTHROPIC_API_KEY: str = Field(...)
    CLAUDE_MODEL: str = "claude-sonnet-4-20250514"
    CLAUDE_MAX_TOKENS: int = 8192
    CLAUDE_TEMPERATURE: float = 0.7
    CLAUDE_STREAMING: bool = True

    # ── PostgreSQL ────────────────────────────────────────────────────────────
    DATABASE_URL: PostgresDsn = Field(...)
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_ECHO: bool = False

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: RedisDsn = Field(...)
    REDIS_CACHE_TTL: int = 3600          # seconds
    REDIS_SESSION_TTL: int = 86400       # seconds

    # ── Qdrant Vector DB ──────────────────────────────────────────────────────
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "knowledge_base"
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DIMENSION: int = 384

    # ── Celery / Workers ──────────────────────────────────────────────────────
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
    WORKER_CONCURRENCY: int = 4

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 60          # seconds

    # ── Observability ─────────────────────────────────────────────────────────
    SENTRY_DSN: str | None = None
    METRICS_ENABLED: bool = True
    TRACE_ENABLED: bool = True

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_origins(cls, v: str | list) -> list:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def qdrant_url(self) -> str:
        return f"http://{self.QDRANT_HOST}:{self.QDRANT_PORT}"


@lru_cache
def get_settings() -> Settings:
    """Cached singleton — import this everywhere."""
    return Settings()


settings = get_settings()
