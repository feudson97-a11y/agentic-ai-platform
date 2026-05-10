"""
Enterprise Agentic AI Platform — LangGraph Supervisor Orchestrator
Graph-based multi-agent orchestration with conditional routing, state
management, retry/fallback, and human-in-the-loop support.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver

from apps.backend.agents.memory_agent import MemoryAgent
from apps.backend.agents.rag_agent import RAGAgent
from apps.backend.agents.automation_agent import AutomationAgent
from apps.backend.agents.recommendation_agent import RecommendationAgent
from apps.backend.agents.analytics_agent import AnalyticsAgent
from apps.backend.agents.notification_agent import NotificationAgent
from apps.backend.core.claude_client import get_claude_client
from apps.backend.core.logging import get_logger

logger = get_logger(__name__)


# ── Routing Enum ──────────────────────────────────────────────────────────────

class AgentRoute(StrEnum):
    MEMORY = "memory"
    RAG = "rag"
    AUTOMATION = "automation"
    RECOMMENDATION = "recommendation"
    ANALYTICS = "analytics"
    NOTIFICATION = "notification"
    RESPOND = "respond"          # direct response, no specialist needed


# ── Graph State ───────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    # LangGraph message accumulator
    messages: Annotated[list[dict], add_messages]

    # Routing & control
    next_agent: str
    iteration: int
    max_iterations: int

    # Task context
    user_id: str
    session_id: str
    task: str
    task_type: str

    # Agent outputs (populated by specialist agents)
    memory_context: str
    rag_context: str
    automation_result: Any
    recommendation_result: Any
    analytics_result: Any
    notification_sent: bool

    # Final assembled response
    final_response: str
    metadata: dict[str, Any]

    # Human-in-the-loop
    awaiting_human: bool
    human_feedback: str | None


# ── Supervisor Prompts ────────────────────────────────────────────────────────

SUPERVISOR_SYSTEM = """You are the Supervisor Agent of an Enterprise Agentic AI Platform.

Your role:
1. Analyse the user task and determine which specialist agent to invoke.
2. Coordinate context from multiple agents when needed.
3. Synthesise a final high-quality response.

Available specialist agents:
- memory: retrieve/store user context and conversation history
- rag: semantic search over the knowledge base
- automation: execute tools, APIs, and background workflows
- recommendation: personalised AI recommendations
- analytics: usage stats, metrics, and reporting
- notification: send emails or alerts
- respond: directly answer without specialist delegation

Rules:
- Always invoke `memory` first for personalised tasks.
- Invoke `rag` when the query requires factual / knowledge retrieval.
- If the task is clearly a direct Q&A with no personalisation needed, route to `respond`.
- Return ONLY valid JSON: {"next": "<agent_name>", "reason": "<brief reason>"}
"""


# ── Node Implementations ──────────────────────────────────────────────────────

class SupervisorOrchestrator:
    """
    LangGraph-powered supervisor that routes tasks to specialist agents,
    aggregates their outputs, and assembles a final response.
    """

    def __init__(self) -> None:
        self.claude = get_claude_client()
        self.memory_agent = MemoryAgent()
        self.rag_agent = RAGAgent()
        self.automation_agent = AutomationAgent()
        self.recommendation_agent = RecommendationAgent()
        self.analytics_agent = AnalyticsAgent()
        self.notification_agent = NotificationAgent()
        self._graph = self._build_graph()

    # ── Graph Builder ─────────────────────────────────────────────────────────

    def _build_graph(self) -> Any:
        graph = StateGraph(AgentState)

        # Register nodes
        graph.add_node("supervisor", self._supervisor_node)
        graph.add_node(AgentRoute.MEMORY, self._memory_node)
        graph.add_node(AgentRoute.RAG, self._rag_node)
        graph.add_node(AgentRoute.AUTOMATION, self._automation_node)
        graph.add_node(AgentRoute.RECOMMENDATION, self._recommendation_node)
        graph.add_node(AgentRoute.ANALYTICS, self._analytics_node)
        graph.add_node(AgentRoute.NOTIFICATION, self._notification_node)
        graph.add_node(AgentRoute.RESPOND, self._respond_node)

        # Entry point
        graph.add_edge(START, "supervisor")

        # Conditional routing from supervisor
        graph.add_conditional_edges(
            "supervisor",
            self._route_decision,
            {
                AgentRoute.MEMORY: AgentRoute.MEMORY,
                AgentRoute.RAG: AgentRoute.RAG,
                AgentRoute.AUTOMATION: AgentRoute.AUTOMATION,
                AgentRoute.RECOMMENDATION: AgentRoute.RECOMMENDATION,
                AgentRoute.ANALYTICS: AgentRoute.ANALYTICS,
                AgentRoute.NOTIFICATION: AgentRoute.NOTIFICATION,
                AgentRoute.RESPOND: AgentRoute.RESPOND,
            },
        )

        # All specialist agents loop back to supervisor for re-evaluation
        for route in AgentRoute:
            if route != AgentRoute.RESPOND:
                graph.add_edge(route, "supervisor")

        graph.add_edge(AgentRoute.RESPOND, END)

        checkpointer = MemorySaver()
        return graph.compile(checkpointer=checkpointer)

    # ── Routing Logic ─────────────────────────────────────────────────────────

    def _route_decision(self, state: AgentState) -> str:
        return state.get("next_agent", AgentRoute.RESPOND)

    # ── Supervisor Node ───────────────────────────────────────────────────────

    async def _supervisor_node(self, state: AgentState) -> dict:
        iteration = state.get("iteration", 0)
        max_iter = state.get("max_iterations", 5)

        if iteration >= max_iter:
            logger.warning("supervisor.max_iterations_reached", iteration=iteration)
            return {"next_agent": AgentRoute.RESPOND, "iteration": iteration + 1}

        context_summary = self._build_context_summary(state)
        messages = [
            {
                "role": "user",
                "content": (
                    f"Task: {state['task']}\n\n"
                    f"Accumulated context:\n{context_summary}\n\n"
                    "Which agent should handle this next? Or should we respond?"
                ),
            }
        ]

        routing = await self.claude.complete_json(
            messages=messages,
            system=SUPERVISOR_SYSTEM,
            response_schema_hint='{"next": "<agent>", "reason": "<string>"}',
        )
        next_agent = routing.get("next", AgentRoute.RESPOND)
        logger.info("supervisor.routing", next=next_agent, reason=routing.get("reason"))

        return {
            "next_agent": next_agent,
            "iteration": iteration + 1,
            "metadata": {**state.get("metadata", {}), f"step_{iteration}": routing},
        }

    # ── Specialist Nodes ──────────────────────────────────────────────────────

    async def _memory_node(self, state: AgentState) -> dict:
        result = await self.memory_agent.run(
            user_id=state["user_id"],
            session_id=state["session_id"],
            task=state["task"],
        )
        return {"memory_context": result, "next_agent": ""}

    async def _rag_node(self, state: AgentState) -> dict:
        result = await self.rag_agent.run(
            query=state["task"],
            context=state.get("memory_context", ""),
        )
        return {"rag_context": result, "next_agent": ""}

    async def _automation_node(self, state: AgentState) -> dict:
        result = await self.automation_agent.run(
            task=state["task"],
            user_id=state["user_id"],
        )
        return {"automation_result": result, "next_agent": ""}

    async def _recommendation_node(self, state: AgentState) -> dict:
        result = await self.recommendation_agent.run(
            user_id=state["user_id"],
            context=state.get("memory_context", ""),
        )
        return {"recommendation_result": result, "next_agent": ""}

    async def _analytics_node(self, state: AgentState) -> dict:
        result = await self.analytics_agent.run(
            user_id=state["user_id"],
            task=state["task"],
        )
        return {"analytics_result": result, "next_agent": ""}

    async def _notification_node(self, state: AgentState) -> dict:
        await self.notification_agent.run(
            user_id=state["user_id"],
            message=state.get("automation_result", state["task"]),
        )
        return {"notification_sent": True, "next_agent": ""}

    async def _respond_node(self, state: AgentState) -> dict:
        """Synthesise the final response from all accumulated context."""
        synthesis_prompt = self._build_synthesis_prompt(state)
        messages = [{"role": "user", "content": synthesis_prompt}]

        response = await self.claude.complete(
            messages=messages,
            system="You are a helpful enterprise AI assistant. Synthesise the provided context into a clear, professional response.",
        )
        from anthropic.types import TextBlock
        final = next(
            (b.text for b in response.content if isinstance(b, TextBlock)), ""
        )
        return {"final_response": final, "next_agent": AgentRoute.RESPOND}

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_context_summary(self, state: AgentState) -> str:
        parts = []
        if ctx := state.get("memory_context"):
            parts.append(f"[Memory Context]\n{ctx}")
        if ctx := state.get("rag_context"):
            parts.append(f"[Knowledge Context]\n{ctx}")
        if res := state.get("automation_result"):
            parts.append(f"[Automation Result]\n{res}")
        if res := state.get("recommendation_result"):
            parts.append(f"[Recommendations]\n{res}")
        if res := state.get("analytics_result"):
            parts.append(f"[Analytics]\n{res}")
        return "\n\n".join(parts) if parts else "No context gathered yet."

    def _build_synthesis_prompt(self, state: AgentState) -> str:
        context = self._build_context_summary(state)
        return (
            f"User task: {state['task']}\n\n"
            f"Gathered context:\n{context}\n\n"
            "Please provide a comprehensive, helpful response."
        )

    # ── Public API ────────────────────────────────────────────────────────────

    async def run(
        self,
        task: str,
        user_id: str,
        session_id: str,
        task_type: str = "general",
    ) -> dict[str, Any]:
        """Execute the full agentic workflow and return the result."""
        initial_state: AgentState = {
            "messages": [],
            "next_agent": "",
            "iteration": 0,
            "max_iterations": 6,
            "user_id": user_id,
            "session_id": session_id,
            "task": task,
            "task_type": task_type,
            "memory_context": "",
            "rag_context": "",
            "automation_result": None,
            "recommendation_result": None,
            "analytics_result": None,
            "notification_sent": False,
            "final_response": "",
            "metadata": {},
            "awaiting_human": False,
            "human_feedback": None,
        }

        config = {"configurable": {"thread_id": session_id}}

        logger.info("orchestrator.run_start", user_id=user_id, session_id=session_id)
        final_state = await self._graph.ainvoke(initial_state, config=config)
        logger.info("orchestrator.run_complete", iterations=final_state["iteration"])

        return {
            "response": final_state["final_response"],
            "metadata": final_state["metadata"],
            "iterations": final_state["iteration"],
        }
