"""Document ingestion into the RAG knowledge base."""
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel
from apps.backend.agents.rag_agent import RAGAgent
from apps.backend.api.deps.auth import get_current_user
from apps.backend.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/documents")
_rag = RAGAgent()

class IngestRequest(BaseModel):
    content: str
    source: str
    metadata: dict = {}

@router.post("/ingest")
async def ingest_text(body: IngestRequest, current_user: dict = Depends(get_current_user)) -> dict:
    doc_id = await _rag.ingest_document(body.content, body.source, metadata=body.metadata)
    return {"doc_id": doc_id, "status": "ingested"}

@router.post("/search")
async def search_docs(query: str, current_user: dict = Depends(get_current_user)) -> dict:
    results = await _rag.search(query)
    return {"results": [{"content": r.content, "source": r.source, "score": r.score} for r in results]}
