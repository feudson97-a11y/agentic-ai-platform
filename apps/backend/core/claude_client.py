"""
Enterprise Agentic AI Platform — Claude API Client
Production-grade Anthropic client with streaming, retry logic, tool calling,
structured outputs, and token-usage observability.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import anthropic
from anthropic import AsyncAnthropic
from anthropic.types import Message, MessageStreamEvent, ToolUseBlock, TextBlock

from apps.backend.core.config import settings
from apps.backend.core.logging import get_logger

logger = get_logger(__name__)


# ── Token Usage Ledger ────────────────────────────────────────────────────────

@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_requests: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def record(self, usage: anthropic.Usage) -> None:
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.total_requests += 1


_global_usage = TokenUsage()


def get_global_usage() -> TokenUsage:
    return _global_usage


# ── Tool Definition Helper ────────────────────────────────────────────────────

def build_tool(
    name: str,
    description: str,
    input_schema: dict[str, Any],
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "input_schema": {"type": "object", **input_schema},
    }


# ── Claude Client ─────────────────────────────────────────────────────────────

class ClaudeClient:
    """
    Async wrapper around Anthropic's Python SDK.

    Features
    --------
    - Streaming and non-streaming completion
    - Tool / function calling with auto-loop
    - Automatic retry with exponential back-off
    - Per-request and global token-usage tracking
    - Structured JSON output extraction
    """

    _MAX_RETRIES = 3
    _BACKOFF_BASE = 2.0

    def __init__(self) -> None:
        self._client = AsyncAnthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            max_retries=0,          # we handle retries ourselves
            timeout=120.0,
        )
        self.model = settings.CLAUDE_MODEL
        self.max_tokens = settings.CLAUDE_MAX_TOKENS
        self.temperature = settings.CLAUDE_TEMPERATURE

    # ── Non-streaming ─────────────────────────────────────────────────────────

    async def complete(
        self,
        messages: list[dict],
        system: str | None = None,
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        metadata: dict | None = None,
    ) -> Message:
        """Single non-streaming completion with retry."""
        kwargs: dict[str, Any] = dict(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            temperature=temperature if temperature is not None else self.temperature,
            messages=messages,
        )
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        for attempt in range(self._MAX_RETRIES):
            try:
                t0 = time.perf_counter()
                response: Message = await self._client.messages.create(**kwargs)
                latency_ms = int((time.perf_counter() - t0) * 1000)
                _global_usage.record(response.usage)
                logger.info(
                    "claude.complete",
                    model=self.model,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    latency_ms=latency_ms,
                    stop_reason=response.stop_reason,
                    **(metadata or {}),
                )
                return response
            except anthropic.RateLimitError as exc:
                wait = self._BACKOFF_BASE ** attempt
                logger.warning("claude.rate_limit", attempt=attempt, wait_s=wait)
                await asyncio.sleep(wait)
            except anthropic.APIStatusError as exc:
                logger.error("claude.api_error", status=exc.status_code, body=exc.body)
                raise
        raise RuntimeError("Claude API: max retries exceeded")

    # ── Streaming ─────────────────────────────────────────────────────────────

    async def stream(
        self,
        messages: list[dict],
        system: str | None = None,
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        """Yield text deltas from a streaming completion."""
        kwargs: dict[str, Any] = dict(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            temperature=temperature if temperature is not None else self.temperature,
            messages=messages,
        )
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text
            final = await stream.get_final_message()
            _global_usage.record(final.usage)

    # ── Tool-calling loop ─────────────────────────────────────────────────────

    async def run_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        tool_executor: "ToolExecutor",
        system: str | None = None,
        max_iterations: int = 10,
    ) -> str:
        """
        Agentic tool-calling loop.

        Repeatedly sends messages to Claude; whenever Claude returns
        tool_use blocks the executor is called and results are appended,
        until Claude returns stop_reason == "end_turn" or max_iterations
        is reached.
        """
        conversation = list(messages)
        for _ in range(max_iterations):
            response = await self.complete(
                messages=conversation,
                system=system,
                tools=tools,
            )

            # Accumulate assistant turn
            conversation.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                # Extract final text
                return next(
                    (block.text for block in response.content if isinstance(block, TextBlock)),
                    "",
                )

            # Execute tool calls in parallel
            tool_blocks = [b for b in response.content if isinstance(b, ToolUseBlock)]
            results = await asyncio.gather(
                *[tool_executor.execute(b.name, b.input) for b in tool_blocks]
            )

            tool_results = [
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(result),
                }
                for block, result in zip(tool_blocks, results)
            ]
            conversation.append({"role": "user", "content": tool_results})

        raise RuntimeError("Tool-calling loop: max iterations exceeded")

    # ── Structured JSON output ────────────────────────────────────────────────

    async def complete_json(
        self,
        messages: list[dict],
        system: str | None = None,
        response_schema_hint: str = "",
    ) -> dict:
        """Ask Claude to return JSON and parse the response."""
        json_system = (
            (system or "")
            + "\n\nYou MUST respond with valid JSON only. No markdown fences, no prose."
            + (f"\nExpected schema: {response_schema_hint}" if response_schema_hint else "")
        )
        import json
        response = await self.complete(messages=messages, system=json_system)
        raw = next(
            (b.text for b in response.content if isinstance(b, TextBlock)), "{}"
        )
        return json.loads(raw.strip())


# ── Tool Executor Protocol ────────────────────────────────────────────────────

class ToolExecutor:
    """Registry + dispatcher for Claude tool calls."""

    def __init__(self) -> None:
        self._handlers: dict[str, Any] = {}

    def register(self, name: str, handler: Any) -> None:
        self._handlers[name] = handler

    async def execute(self, name: str, inputs: dict) -> Any:
        handler = self._handlers.get(name)
        if handler is None:
            return f"Error: unknown tool '{name}'"
        try:
            if asyncio.iscoroutinefunction(handler):
                return await handler(**inputs)
            return handler(**inputs)
        except Exception as exc:
            logger.error("tool.execution_error", tool=name, error=str(exc))
            return f"Error executing {name}: {exc}"


# ── Singleton ─────────────────────────────────────────────────────────────────

_claude_client: ClaudeClient | None = None


def get_claude_client() -> ClaudeClient:
    global _claude_client
    if _claude_client is None:
        _claude_client = ClaudeClient()
    return _claude_client
