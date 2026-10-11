"""Smoke tests: the FastAPI app boots and the health endpoints respond."""

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-32-chars-long!!")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from fastapi.testclient import TestClient  # noqa: E402

from apps.backend.api.main import app  # noqa: E402
from apps.backend.core.config import settings  # noqa: E402

client = TestClient(app)


def test_health() -> None:
    response = client.get(f"{settings.API_PREFIX}/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == settings.APP_VERSION


def test_ready() -> None:
    response = client.get(f"{settings.API_PREFIX}/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_openapi_lists_core_routes() -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert f"{settings.API_PREFIX}/health" in paths
