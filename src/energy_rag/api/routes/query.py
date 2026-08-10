"""Query endpoint for RAG."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from energy_rag.api.schemas import QueryRequest, QueryResponse, SourceResponse
from energy_rag.config import settings
from energy_rag.retrieval.chain import query_rag

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/query", tags=["query"])

# Global references (initialized on startup)
_vector_store = None
_llm = None


def set_dependencies(vector_store, llm):
    """Set global dependencies (called from main.py on startup)."""
    global _vector_store, _llm
    _vector_store = vector_store
    _llm = llm


@router.post("", response_model=QueryResponse)
async def query_rag_endpoint(request: QueryRequest) -> QueryResponse:
    """
    Query the RAG system.

    Returns an answer with source citations based on retrieved documents.
    """
    if _vector_store is None or _llm is None:
        raise HTTPException(
            status_code=503,
            detail="RAG system not initialized. Check service logs.",
        )

    try:
        result = await query_rag(
            vector_store=_vector_store,
            llm=_llm,
            question=request.query,
            top_k=request.top_k,
            filters=request.filters,
            include_citations=request.include_citations,
        )

        sources = [
            SourceResponse(index=s["index"], content=s["content"], metadata=s["metadata"])
            for s in result.get("sources", [])
        ]

        return QueryResponse(
            answer=result["answer"],
            sources=sources,
            processing_time_ms=result["processing_time_ms"],
        )

    except Exception as exc:
        logger.exception("Query failed")
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/stats")
async def query_stats() -> dict[str, Any]:
    """Get query service statistics."""
    return {
        "embedding_model": settings.embedding_model,
        "embedding_dimension": settings.embedding_dimension,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "default_top_k": settings.default_top_k,
        "similarity_threshold": settings.similarity_threshold,
    }
