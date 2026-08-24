"""Query endpoint for RAG."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from energy_rag.api.schemas import (
    QueryRequest,
    QueryResponse,
    SearchRequest,
    SearchResponse,
    SourceResponse,
)
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


@router.post("/search", response_model=SearchResponse)
async def search_endpoint(request: SearchRequest) -> SearchResponse:
    """
    Pure semantic retrieval without LLM generation.

    Useful when no LLM provider is configured (NAS deployments) or for
    building custom pipelines on top of the vector store.
    """
    import time

    if _vector_store is None:
        raise HTTPException(
            status_code=503,
            detail="RAG system not initialized. Check service logs.",
        )

    start_time = time.perf_counter()

    try:
        docs_with_scores = await _vector_store.asimilarity_search(
            request.query,
            k=request.top_k,
            filter=request.filters,
        )
        results = [
            SourceResponse(index=i, content=doc.page_content, metadata=doc.metadata)
            for i, doc in enumerate(docs_with_scores, 1)
        ]
        return SearchResponse(
            results=results,
            processing_time_ms=int((time.perf_counter() - start_time) * 1000),
        )
    except Exception as exc:
        logger.exception("Search failed")
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
