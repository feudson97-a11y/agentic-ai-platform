"""
Enterprise Agentic AI Platform — FastAPI Application Entry Point
Production-grade app factory with middleware, observability, and WebSocket support.
"""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from apps.backend.api.v1.endpoints import agents, auth, documents, health, workflows
from apps.backend.core.config import settings
from apps.backend.core.logging import configure_logging, get_logger, new_request_id

configure_logging()
logger = get_logger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown hooks."""
    logger.info("app.startup", environment=settings.ENVIRONMENT, version=settings.APP_VERSION)
    # Warm-up: verify DB, Redis, Qdrant connections here in production
    yield
    logger.info("app.shutdown")


# ── App Factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Enterprise Agentic AI Platform — Multi-agent Claude orchestration",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── Middleware stack (order matters — outermost first) ────────────────────
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(o) for o in settings.ALLOWED_ORIGINS] or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next: Any) -> Response:
        rid = new_request_id()
        request.state.request_id = rid
        t0 = time.perf_counter()
        response: Response = await call_next(request)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Response-Time-Ms"] = str(latency_ms)
        logger.info(
            "http.request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            latency_ms=latency_ms,
        )
        return response

    # ── Routers ───────────────────────────────────────────────────────────────
    prefix = settings.API_PREFIX
    app.include_router(health.router, prefix=prefix, tags=["Health"])
    app.include_router(auth.router, prefix=prefix, tags=["Authentication"])
    app.include_router(agents.router, prefix=prefix, tags=["Agents"])
    app.include_router(documents.router, prefix=prefix, tags=["Documents"])
    app.include_router(workflows.router, prefix=prefix, tags=["Workflows"])

    # ── Prometheus metrics ────────────────────────────────────────────────────
    if settings.METRICS_ENABLED:
        Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    # ── Global exception handler ──────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled_exception", path=request.url.path, error=str(exc), exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": getattr(request.state, "request_id", "")},
        )

    # ── WebSocket: real-time agent streaming ──────────────────────────────────
    @app.websocket("/ws/agents/{session_id}")
    async def agent_stream(websocket: WebSocket, session_id: str) -> None:
        await websocket.accept()
        from apps.backend.core.claude_client import get_claude_client
        claude = get_claude_client()
        try:
            while True:
                data = await websocket.receive_json()
                task = data.get("task", "")
                messages = [{"role": "user", "content": task}]
                async for chunk in claude.stream(messages=messages):
                    await websocket.send_json({"type": "chunk", "data": chunk})
                await websocket.send_json({"type": "done"})
        except WebSocketDisconnect:
            logger.info("websocket.disconnect", session_id=session_id)

    return app


app = create_app()
