"""
API v1 — Agents Router
Endpoints for running agentic workflows via HTTP and streaming.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from apps.backend.agents.orchestrator import SupervisorOrchestrator
from apps.backend.api.deps.auth import get_current_user
from apps.backend.core.claude_client import get_claude_client
from apps.backend.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/agents")

# ── Schemas ───────────────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=8192, description="The task for the agent system")
    task_type: str = Field(default="general", description="Hint for the supervisor router")
    session_id: str | None = Field(default=None, description="Conversation session ID; auto-generated if omitted")
    stream: bool = Field(default=False, description="Enable streaming response")


class RunResponse(BaseModel):
    session_id: str
    response: str
    iterations: int
    metadata: dict[str, Any]


# ── Singleton orchestrator (shared across requests) ───────────────────────────
_orchestrator: SupervisorOrchestrator | None = None

def get_orchestrator() -> SupervisorOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = SupervisorOrchestrator()
    return _orchestrator


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/run", response_model=RunResponse, status_code=status.HTTP_200_OK)
async def run_agent(
    body: RunRequest,
    current_user: dict = Depends(get_current_user),
    orchestrator: SupervisorOrchestrator = Depends(get_orchestrator),
) -> RunResponse:
    """
    Submit a task to the multi-agent supervisor.
    The orchestrator routes through specialist agents and returns a synthesised response.
    """
    session_id = body.session_id or str(uuid4())
    user_id = current_user["sub"]

    logger.info("agents.run", user_id=user_id, session_id=session_id, task_type=body.task_type)

    try:
        result = await orchestrator.run(
            task=body.task,
            user_id=user_id,
            session_id=session_id,
            task_type=body.task_type,
        )
    except Exception as exc:
        logger.error("agents.run_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return RunResponse(
        session_id=session_id,
        response=result["response"],
        iterations=result["iterations"],
        metadata=result["metadata"],
    )


@router.post("/stream")
async def stream_agent(
    body: RunRequest,
    current_user: dict = Depends(get_current_user),
) -> StreamingResponse:
    """
    Stream Claude's response token-by-token via Server-Sent Events.
    """
    claude = get_claude_client()
    messages = [{"role": "user", "content": body.task}]

    async def event_generator():
        async for chunk in claude.stream(messages=messages):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/usage")
async def get_usage(current_user: dict = Depends(get_current_user)) -> dict:
    """Return global Claude API token-usage statistics."""
    from apps.backend.core.claude_client import get_global_usage
    u = get_global_usage()
    return {
        "total_requests": u.total_requests,
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
        "total_tokens": u.total_tokens,
    }
