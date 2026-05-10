"""
Enterprise Agentic AI Platform — Structured Logging
JSON-structured logs for production observability stacks (Datadog, CloudWatch, etc.).
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any
from uuid import uuid4

import structlog

from apps.backend.core.config import settings

# ── Context variables (propagated through async call stacks) ─────────────────
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")
agent_id_var: ContextVar[str] = ContextVar("agent_id", default="")


def _add_context(
    logger: Any, method: str, event_dict: dict
) -> dict:
    """Inject shared context vars into every log entry."""
    if rid := request_id_var.get():
        event_dict["request_id"] = rid
    if uid := user_id_var.get():
        event_dict["user_id"] = uid
    if aid := agent_id_var.get():
        event_dict["agent_id"] = aid
    event_dict["environment"] = settings.ENVIRONMENT
    event_dict["app_version"] = settings.APP_VERSION
    return event_dict


def configure_logging() -> None:
    """Bootstrap structlog — call once at application startup."""
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        _add_context,
    ]

    if settings.is_production:
        # Machine-readable JSON for log aggregators
        renderer = structlog.processors.JSONRenderer()
    else:
        # Human-friendly coloured output for local dev
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.LOG_LEVEL)
        ),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.LOG_LEVEL)

    # Quieten noisy third-party loggers
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)


def new_request_id() -> str:
    rid = str(uuid4())
    request_id_var.set(rid)
    return rid
