"""
Enterprise Agentic AI Platform — RAG Knowledge Agent
Semantic search, document ingestion, chunking, embedding, and context retrieval.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    ScoredPoint,
    VectorParams,
    Filter,
    FieldCondition,
    MatchValue,
)
from sentence_transformers import SentenceTransformer

from apps.backend.core.config import settings
from apps.backend.core.logging import get_logger

logger = get_logger(__name__)


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class DocumentChunk:
    chunk_id: str
    doc_id: str
    content: str
    embedding: list[float]
    metadata: dict[str, Any]


@dataclass
class RetrievedContext:
    content: str
    source: str
    score: float
    metadata: dict[str, Any]


# ── Embedding Service ─────────────────────────────────────────────────────────

class EmbeddingService:
    """Wraps sentence-transformers for synchronous and async encoding."""

    def __init__(self) -> None:
        self._model: SentenceTransformer | None = None

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            logger.info("embedding.loading_model", name=settings.EMBEDDING_MODEL)
            self._model = SentenceTransformer(settings.EMBEDDING_MODEL)
        return self._model

    def encode(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, show_progress_bar=False).tolist()

    def encode_single(self, text: str) -> list[float]:
        return self.encode([text])[0]


# ── RAG Agent ─────────────────────────────────────────────────────────────────

class RAGAgent:
    """
    Full RAG pipeline:
    1. Ingest documents → chunk → embed → store in Qdrant
    2. At query time: embed query → semantic search → inject top-k context
    """

    def __init__(self) -> None:
        self._qdrant: AsyncQdrantClient | None = None
        self.embeddings = EmbeddingService()
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=512,
            chunk_overlap=64,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    @property
    def qdrant(self) -> AsyncQdrantClient:
        if self._qdrant is None:
            self._qdrant = AsyncQdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
            )
        return self._qdrant

    # ── Collection management ─────────────────────────────────────────────────

    async def ensure_collection(self) -> None:
        existing = await self.qdrant.get_collections()
        names = [c.name for c in existing.collections]
        if settings.QDRANT_COLLECTION not in names:
            await self.qdrant.create_collection(
                collection_name=settings.QDRANT_COLLECTION,
                vectors_config=VectorParams(
                    size=settings.EMBEDDING_DIMENSION,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("qdrant.collection_created", name=settings.QDRANT_COLLECTION)

    # ── Ingestion ─────────────────────────────────────────────────────────────

    async def ingest_document(
        self,
        content: str,
        source: str,
        doc_id: str | None = None,
        metadata: dict | None = None,
    ) -> str:
        """Chunk, embed, and upsert a document into Qdrant."""
        await self.ensure_collection()

        doc_id = doc_id or hashlib.sha256(content.encode()).hexdigest()[:16]
        chunks = self.splitter.split_text(content)
        texts = [c for c in chunks if c.strip()]

        logger.info("rag.ingest_start", doc_id=doc_id, chunks=len(texts))

        embeddings = self.embeddings.encode(texts)
        points: list[PointStruct] = []
        for i, (text, vector) in enumerate(zip(texts, embeddings)):
            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload={
                        "doc_id": doc_id,
                        "source": source,
                        "chunk_index": i,
                        "content": text,
                        **(metadata or {}),
                    },
                )
            )

        await self.qdrant.upsert(
            collection_name=settings.QDRANT_COLLECTION,
            points=points,
        )
        logger.info("rag.ingest_complete", doc_id=doc_id, vectors=len(points))
        return doc_id

    # ── Retrieval ─────────────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.5,
        filter_source: str | None = None,
    ) -> list[RetrievedContext]:
        """Embed query and return top-k semantically similar chunks."""
        await self.ensure_collection()

        query_vector = self.embeddings.encode_single(query)

        search_filter = None
        if filter_source:
            search_filter = Filter(
                must=[FieldCondition(key="source", match=MatchValue(value=filter_source))]
            )

        results: list[ScoredPoint] = await self.qdrant.search(
            collection_name=settings.QDRANT_COLLECTION,
            query_vector=query_vector,
            limit=top_k,
            score_threshold=score_threshold,
            query_filter=search_filter,
        )

        retrieved = [
            RetrievedContext(
                content=r.payload.get("content", ""),
                source=r.payload.get("source", "unknown"),
                score=r.score,
                metadata={k: v for k, v in r.payload.items() if k != "content"},
            )
            for r in results
        ]

        logger.info("rag.search", query_len=len(query), results=len(retrieved))
        return retrieved

    # ── Context formatting ────────────────────────────────────────────────────

    def format_context(self, results: list[RetrievedContext]) -> str:
        if not results:
            return "No relevant documents found in the knowledge base."
        parts = []
        for i, r in enumerate(results, 1):
            parts.append(
                f"[{i}] Source: {r.source} (score: {r.score:.3f})\n{r.content}"
            )
        return "\n\n---\n\n".join(parts)

    # ── Agent entrypoint ──────────────────────────────────────────────────────

    async def run(self, query: str, context: str = "") -> str:
        """Retrieve relevant knowledge and return formatted context string."""
        enriched_query = f"{context}\n\nQuestion: {query}".strip() if context else query
        results = await self.search(enriched_query, top_k=5)
        return self.format_context(results)
