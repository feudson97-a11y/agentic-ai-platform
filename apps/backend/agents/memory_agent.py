"""
Enterprise Agentic AI Platform — Memory Agent
Hierarchical memory: Redis (short-term / session) + PostgreSQL (long-term / user).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from apps.backend.core.config import settings
from apps.backend.core.logging import get_logger

logger = get_logger(__name__)

# ── Short-term Memory (Redis) ─────────────────────────────────────────────────

class ShortTermMemory:
    """
    Stores the active conversation turns in Redis with a TTL.
    Key pattern: memory:{user_id}:{session_id}
    """

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis
        self._ttl = settings.REDIS_SESSION_TTL

    def _key(self, user_id: str, session_id: str) -> str:
        return f"memory:{user_id}:{session_id}"

    async def append(self, user_id: str, session_id: str, role: str, content: str) -> None:
        key = self._key(user_id, session_id)
        turn = json.dumps({"role": role, "content": content, "ts": datetime.now(timezone.utc).isoformat()})
        await self._redis.rpush(key, turn)
        await self._redis.expire(key, self._ttl)

    async def get_turns(self, user_id: str, session_id: str, last_n: int = 20) -> list[dict]:
        key = self._key(user_id, session_id)
        raw = await self._redis.lrange(key, -last_n, -1)
        return [json.loads(r) for r in raw]

    async def clear(self, user_id: str, session_id: str) -> None:
        await self._redis.delete(self._key(user_id, session_id))


# ── Long-term Memory (PostgreSQL) ─────────────────────────────────────────────

class LongTermMemory:
    """
    Persists distilled user facts and preferences to PostgreSQL.
    Queried at the start of each session to personalise responses.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def store_fact(self, user_id: str, fact: str, category: str = "general") -> None:
        from sqlalchemy import text
        await self._db.execute(
            text(
                """
                INSERT INTO user_memories (user_id, fact, category, created_at)
                VALUES (:user_id, :fact, :category, NOW())
                ON CONFLICT DO NOTHING
                """
            ),
            {"user_id": user_id, "fact": fact, "category": category},
        )
        await self._db.commit()

    async def get_facts(self, user_id: str, limit: int = 10) -> list[dict]:
        from sqlalchemy import text
        result = await self._db.execute(
            text(
                """
                SELECT fact, category, created_at
                FROM user_memories
                WHERE user_id = :user_id
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"user_id": user_id, "limit": limit},
        )
        return [dict(row._mapping) for row in result]

    async def get_interaction_history(self, user_id: str, limit: int = 5) -> list[dict]:
        from sqlalchemy import text
        result = await self._db.execute(
            text(
                """
                SELECT task, response_summary, created_at
                FROM interaction_history
                WHERE user_id = :user_id
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"user_id": user_id, "limit": limit},
        )
        return [dict(row._mapping) for row in result]


# ── Memory Agent ──────────────────────────────────────────────────────────────

class MemoryAgent:
    """
    Unified interface over short-term (Redis) and long-term (PostgreSQL) memory.
    Exposed to the LangGraph orchestrator as a specialist node.
    """

    def __init__(self) -> None:
        self._redis_pool: aioredis.ConnectionPool | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis_pool is None:
            self._redis_pool = aioredis.ConnectionPool.from_url(
                str(settings.REDIS_URL), decode_responses=True
            )
        return aioredis.Redis(connection_pool=self._redis_pool)

    async def run(self, user_id: str, session_id: str, task: str) -> str:
        """Retrieve and format all relevant memory for the given user/session."""
        redis = await self._get_redis()
        stm = ShortTermMemory(redis)

        recent_turns = await stm.get_turns(user_id, session_id, last_n=10)

        context_parts: list[str] = []

        if recent_turns:
            formatted = "\n".join(
                f"{t['role'].upper()}: {t['content']}" for t in recent_turns
            )
            context_parts.append(f"[Recent Conversation]\n{formatted}")

        # Long-term memory requires a DB session — injected lazily in production
        # Here we emit a placeholder; real implementation wires the DB session via FastAPI DI
        context_parts.append("[Long-term Memory] User profile context would appear here.")

        logger.info("memory_agent.run", user_id=user_id, turns=len(recent_turns))
        return "\n\n".join(context_parts) if context_parts else "No prior context available."

    async def store_turn(
        self, user_id: str, session_id: str, role: str, content: str
    ) -> None:
        redis = await self._get_redis()
        stm = ShortTermMemory(redis)
        await stm.append(user_id, session_id, role, content)
