"""Workflow history and management."""
from fastapi import APIRouter, Depends
from apps.backend.api.deps.auth import get_current_user

router = APIRouter(prefix="/workflows")

@router.get("/")
async def list_workflows(current_user: dict = Depends(get_current_user)) -> dict:
    # Stub — wire to PostgreSQL workflow_history table
    return {"workflows": [], "total": 0}
