from fastapi import APIRouter
from apps.backend.core.config import settings

router = APIRouter()

@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": settings.APP_VERSION, "environment": settings.ENVIRONMENT}

@router.get("/ready")
async def ready() -> dict:
    # Add DB/Redis connectivity checks in production
    return {"status": "ready"}
