# 🤖 Enterprise Agentic AI Platform

> **Production-grade multi-agent AI system** powered by Claude (Anthropic), LangGraph, FastAPI, and a full observability stack — built for autonomous workflow orchestration at enterprise scale.

[![CI/CD](https://github.com/your-org/agentic-ai-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/agentic-ai-platform/actions)
[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![Claude](https://img.shields.io/badge/Claude-Sonnet%204-blueviolet.svg)](https://anthropic.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Client Layer                              │
│          Next.js · WebSockets · REST · SSE Streaming            │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                   Nginx Reverse Proxy                            │
│              Rate limiting · TLS · Load balancing                │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                  FastAPI Backend (Async)                          │
│   JWT Auth · RBAC · WebSockets · Prometheus · Structured Logs    │
└──────────┬───────────────────────────────────────┬──────────────┘
           │                                       │
┌──────────▼──────────┐                 ┌──────────▼──────────────┐
│  LangGraph          │                 │  Celery Workers          │
│  Supervisor Agent   │                 │  Background tasks        │
│  ┌───────────────┐  │                 │  Scheduled jobs          │
│  │ Memory Agent  │  │                 └─────────────────────────┘
│  │ RAG Agent     │  │
│  │ Automation    │  │
│  │ Recommend.    │  │
│  │ Analytics     │  │
│  │ Notification  │  │
│  └───────────────┘  │
│  Claude API ────────┤
└──────────┬──────────┘
           │
┌──────────▼──────────────────────────────────────────────────────┐
│                     Data Layer                                   │
│  PostgreSQL (users · history)  Redis (cache · sessions · queue)  │
│  Qdrant (vector embeddings · semantic search)                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Features

### 🧠 Multi-Agent Orchestration (LangGraph)
- **Supervisor Agent** — central router with conditional graph traversal
- **Memory Agent** — hierarchical short-term (Redis) and long-term (PostgreSQL) memory
- **RAG Knowledge Agent** — document ingestion, chunking, Qdrant vector search
- **Automation Agent** — tool-calling loop with parallel tool execution
- **Recommendation Agent** — personalised AI-driven suggestions
- **Analytics Agent** — token usage, metrics, and platform reporting
- **Notification Agent** — AI-generated email and alert composition

### 🔌 Claude Integration
- Streaming and non-streaming completions
- Agentic tool-calling loop with retry + fallback
- Structured JSON output extraction
- Token usage tracking per request and globally
- Exponential back-off on rate limits

### 🏗 Enterprise Backend
- FastAPI with full async/await, WebSocket streaming, and SSE
- JWT authentication with access/refresh token rotation
- RBAC permissions and audit logging
- Rate limiting at Nginx and application layer
- Prometheus metrics + structured JSON logs (structlog)

### 🗄 Data Infrastructure
- PostgreSQL with Alembic migrations
- Redis for caching, sessions, and Celery queues
- Qdrant for vector storage and semantic retrieval
- sentence-transformers for local embeddings (no external API needed)

### 🚀 DevOps
- Multi-stage Docker builds (minimal runtime image)
- Docker Compose for full local stack
- Kubernetes-ready architecture
- GitHub Actions CI/CD (lint → test → build → deploy)

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.12+
- Anthropic API key

### 1. Clone and configure
```bash
git clone https://github.com/your-org/agentic-ai-platform.git
cd agentic-ai-platform
cp .env.example .env
# Edit .env — add your ANTHROPIC_API_KEY and generate a SECRET_KEY
openssl rand -hex 32  # paste output as SECRET_KEY
```

### 2. Start the full stack
```bash
docker compose up -d
```

Services started:
| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| API | http://localhost/api/v1 |
| API Docs | http://localhost:8000/docs |
| Qdrant Dashboard | http://localhost:6333/dashboard |
| Prometheus Metrics | http://localhost/metrics |

### 3. Run an agent task
```bash
# Get a token
TOKEN=$(curl -s -X POST http://localhost/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"changeme"}' | jq -r .access_token)

# Run a multi-agent task
curl -X POST http://localhost/api/v1/agents/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"task": "Summarise the latest AI research and give me recommendations", "task_type": "research"}'
```

---

## Project Structure

```
agentic-ai-platform/
├── apps/
│   ├── backend/
│   │   ├── agents/
│   │   │   ├── orchestrator.py        # LangGraph supervisor graph
│   │   │   ├── memory_agent.py        # Redis + PostgreSQL memory
│   │   │   ├── rag_agent.py           # Qdrant RAG pipeline
│   │   │   └── specialist_agents.py   # Automation, Rec, Analytics, Notif
│   │   ├── api/
│   │   │   ├── main.py                # FastAPI app factory
│   │   │   ├── v1/endpoints/          # REST + WebSocket routers
│   │   │   ├── middleware/            # Rate limit, logging, tracing
│   │   │   └── deps/                  # JWT auth dependency
│   │   └── core/
│   │       ├── config.py              # Pydantic settings
│   │       ├── claude_client.py       # Anthropic SDK wrapper
│   │       └── logging.py             # structlog setup
│   └── frontend/                      # Next.js + TailwindCSS + TypeScript
├── infrastructure/
│   ├── docker/                        # Multi-stage Dockerfiles
│   ├── k8s/                           # Kubernetes manifests
│   └── nginx/                         # Reverse proxy config
├── database/
│   └── schemas/                       # PostgreSQL DDL
├── ai/
│   ├── prompts/                        # System prompt templates
│   └── tools/                          # Tool definitions
├── docs/
│   ├── architecture/                   # Architecture diagrams
│   └── api/                            # OpenAPI docs
├── .github/workflows/ci.yml            # GitHub Actions
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## API Reference

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/login` | Get access + refresh tokens |
| POST | `/api/v1/auth/refresh` | Rotate access token |

### Agents
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/agents/run` | Submit task to supervisor orchestrator |
| POST | `/api/v1/agents/stream` | Streaming Claude response (SSE) |
| GET | `/api/v1/agents/usage` | Token usage statistics |
| WS | `/ws/agents/{session_id}` | Real-time WebSocket streaming |

### Documents (RAG)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/documents/ingest` | Add document to knowledge base |
| POST | `/api/v1/documents/search` | Semantic search |

### Observability
| Endpoint | Description |
|----------|-------------|
| `/api/v1/health` | Liveness probe |
| `/api/v1/ready` | Readiness probe |
| `/metrics` | Prometheus metrics |

---

## Configuration

All configuration is via environment variables (see `.env.example`). Key settings:

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `CLAUDE_MODEL` | Model string (default: `claude-sonnet-4-20250514`) |
| `DATABASE_URL` | PostgreSQL connection string (asyncpg) |
| `REDIS_URL` | Redis connection string |
| `QDRANT_HOST` / `QDRANT_PORT` | Qdrant vector DB |
| `SECRET_KEY` | JWT signing key (min 32 chars) |
| `ENVIRONMENT` | `development` / `staging` / `production` |

---

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Start infrastructure only
docker compose up -d postgres redis qdrant

# Run backend in dev mode
uvicorn apps.backend.api.main:app --reload --port 8000

# Run tests
pytest tests/ -v --cov=apps/backend

# Lint
ruff check apps/backend
mypy apps/backend
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| AI Reasoning | Claude Sonnet (Anthropic) |
| Orchestration | LangGraph + LangChain |
| Backend | FastAPI + Python 3.12 + AsyncIO |
| Task Queue | Celery + Redis |
| Vector DB | Qdrant |
| Embeddings | sentence-transformers |
| Primary DB | PostgreSQL + SQLAlchemy |
| Cache | Redis |
| Auth | JWT (python-jose) |
| Observability | structlog + Prometheus |
| Frontend | Next.js + TypeScript + TailwindCSS |
| Proxy | Nginx |
| Container | Docker + Docker Compose |
| CI/CD | GitHub Actions |

---

## Roadmap

- [ ] MCP (Model Context Protocol) tool server integration
- [ ] Human-in-the-loop workflow pausing via LangGraph interrupts  
- [ ] Multi-tenant RBAC with workspace isolation
- [ ] Kubernetes Helm chart
- [ ] OpenTelemetry distributed tracing
- [ ] Fine-tuned domain-specific embedding models
- [ ] A/B testing framework for agent routing strategies

---

## License

MIT © 2025 — Enterprise Agentic AI Platform
