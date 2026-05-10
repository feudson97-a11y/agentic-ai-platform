"""
Enterprise Agentic AI Platform — Specialist Agents
Automation · Recommendation · Analytics · Notification
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from apps.backend.core.claude_client import get_claude_client, ToolExecutor, build_tool
from apps.backend.core.logging import get_logger

logger = get_logger(__name__)


# ── Automation Agent ──────────────────────────────────────────────────────────

class AutomationAgent:
    """
    Executes tool-driven workflows autonomously.
    Wraps Claude's tool-calling loop with a pre-registered tool registry.
    """

    SYSTEM = """You are an Automation Agent. Execute the user's request by calling
the appropriate tools. Be precise, handle errors gracefully, and confirm completion."""

    def __init__(self) -> None:
        self.claude = get_claude_client()
        self.executor = ToolExecutor()
        self._register_tools()

    def _register_tools(self) -> None:
        self.executor.register("web_search", self._tool_web_search)
        self.executor.register("send_http_request", self._tool_http_request)
        self.executor.register("transform_data", self._tool_transform_data)
        self.executor.register("schedule_task", self._tool_schedule_task)

    @property
    def tools(self) -> list[dict]:
        return [
            build_tool(
                "web_search",
                "Search the web for current information.",
                {"properties": {"query": {"type": "string", "description": "Search query"}}, "required": ["query"]},
            ),
            build_tool(
                "send_http_request",
                "Send an HTTP request to an external API.",
                {
                    "properties": {
                        "url": {"type": "string"},
                        "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"]},
                        "payload": {"type": "object"},
                    },
                    "required": ["url", "method"],
                },
            ),
            build_tool(
                "transform_data",
                "Transform or process a JSON data payload.",
                {
                    "properties": {
                        "data": {"type": "object"},
                        "operation": {"type": "string", "description": "e.g. 'summarise', 'filter', 'sort'"},
                    },
                    "required": ["data", "operation"],
                },
            ),
            build_tool(
                "schedule_task",
                "Schedule a background task for later execution.",
                {
                    "properties": {
                        "task_name": {"type": "string"},
                        "payload": {"type": "object"},
                        "delay_seconds": {"type": "integer"},
                    },
                    "required": ["task_name"],
                },
            ),
        ]

    # ── Tool implementations ──────────────────────────────────────────────────

    async def _tool_web_search(self, query: str) -> str:
        # Stub — wire to a real search API (SerpAPI, Tavily, etc.)
        logger.info("automation.web_search", query=query)
        return f"[Search results for: {query}] — integrate SerpAPI/Tavily for live results."

    async def _tool_http_request(
        self, url: str, method: str = "GET", payload: dict | None = None
    ) -> str:
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(method, url, json=payload)
            return resp.text[:2000]

    async def _tool_transform_data(self, data: dict, operation: str) -> str:
        messages = [
            {
                "role": "user",
                "content": f"Operation: {operation}\nData: {json.dumps(data)}\nReturn transformed result as JSON.",
            }
        ]
        result = await self.claude.complete_json(messages)
        return json.dumps(result)

    async def _tool_schedule_task(
        self, task_name: str, payload: dict | None = None, delay_seconds: int = 0
    ) -> str:
        # Stub — wire to Celery in production
        logger.info("automation.schedule", task=task_name, delay=delay_seconds)
        return f"Task '{task_name}' scheduled (delay: {delay_seconds}s)"

    async def run(self, task: str, user_id: str) -> str:
        messages = [{"role": "user", "content": task}]
        result = await self.claude.run_with_tools(
            messages=messages,
            tools=self.tools,
            tool_executor=self.executor,
            system=self.SYSTEM,
        )
        logger.info("automation.complete", user_id=user_id)
        return result


# ── Recommendation Agent ──────────────────────────────────────────────────────

class RecommendationAgent:
    """Generates personalised AI recommendations based on user context."""

    SYSTEM = """You are a Recommendation Agent. Analyse the user's context and
provide 3-5 specific, actionable recommendations. Format as JSON:
{"recommendations": [{"title": "...", "description": "...", "priority": "high|medium|low"}]}"""

    def __init__(self) -> None:
        self.claude = get_claude_client()

    async def run(self, user_id: str, context: str) -> str:
        messages = [
            {
                "role": "user",
                "content": (
                    f"User context:\n{context}\n\n"
                    "Generate personalised recommendations for this user."
                ),
            }
        ]
        result = await self.claude.complete_json(messages, system=self.SYSTEM)
        recs = result.get("recommendations", [])
        formatted = "\n".join(
            f"• [{r.get('priority','').upper()}] {r.get('title')}: {r.get('description')}"
            for r in recs
        )
        logger.info("recommendation.complete", user_id=user_id, count=len(recs))
        return formatted or "No recommendations generated."


# ── Analytics Agent ───────────────────────────────────────────────────────────

class AnalyticsAgent:
    """Tracks AI usage metrics and generates reports."""

    def __init__(self) -> None:
        self.claude = get_claude_client()

    async def run(self, user_id: str, task: str) -> str:
        # In production: query PostgreSQL/ClickHouse for real metrics
        from apps.backend.core.claude_client import get_global_usage
        usage = get_global_usage()
        summary = (
            f"Platform Usage Stats\n"
            f"  Total requests : {usage.total_requests}\n"
            f"  Input tokens   : {usage.input_tokens:,}\n"
            f"  Output tokens  : {usage.output_tokens:,}\n"
            f"  Total tokens   : {usage.total_tokens:,}\n"
            f"  Timestamp      : {datetime.now(timezone.utc).isoformat()}"
        )
        logger.info("analytics.run", user_id=user_id)
        return summary


# ── Notification Agent ────────────────────────────────────────────────────────

class NotificationAgent:
    """Sends AI-generated email notifications and alerts."""

    SYSTEM = """You are a Notification Agent. Compose a brief, professional
notification message based on the provided event. Be concise and actionable."""

    def __init__(self) -> None:
        self.claude = get_claude_client()

    async def run(self, user_id: str, message: str) -> None:
        messages = [{"role": "user", "content": f"Event: {message}\nCompose notification."}]
        response = await self.claude.complete(messages=messages, system=self.SYSTEM)

        from anthropic.types import TextBlock
        body = next((b.text for b in response.content if isinstance(b, TextBlock)), "")

        # Stub — wire to SendGrid / SES / Resend in production
        logger.info("notification.sent", user_id=user_id, preview=body[:80])
