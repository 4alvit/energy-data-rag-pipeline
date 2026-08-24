"""Pydantic schemas for API requests and responses."""

from typing import Any

from pydantic import BaseModel, Field

from energy_rag import __version__


class QueryRequest(BaseModel):
    """Request model for RAG query."""

    query: str = Field(..., min_length=1, max_length=2000, description="User question")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of documents to retrieve")
    filters: dict[str, Any] | None = Field(default=None, description="Metadata filters")
    include_citations: bool = Field(
        default=True, description="Include source citations in response"
    )


class SourceResponse(BaseModel):
    """Source document in response."""

    index: int
    content: str
    metadata: dict[str, Any]


class QueryResponse(BaseModel):
    """Response model for RAG query."""

    answer: str
    sources: list[SourceResponse] = []
    processing_time_ms: int


class SearchRequest(BaseModel):
    """Request model for pure semantic retrieval (no LLM)."""

    query: str = Field(..., min_length=1, max_length=2000, description="User question")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of documents to retrieve")
    filters: dict[str, Any] | None = Field(default=None, description="Metadata filters")


class SearchResponse(BaseModel):
    """Response model for semantic retrieval."""

    results: list[SourceResponse] = []
    processing_time_ms: int


class IngestRequest(BaseModel):
    """Request model for document ingestion."""

    source_type: str = Field(..., pattern="^(pdf|forum_html|forum_json|url)$")
    paths: list[str] = Field(..., min_length=1, description="File paths or URLs to ingest")
    chunk_strategy: str | None = Field(default="technical", description="Chunking strategy")


class IngestResponse(BaseModel):
    """Response model for document ingestion."""

    status: str
    documents_processed: int
    chunks_created: int
    run_id: str | None = None
    error_message: str | None = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    database: str
    version: str = __version__


class ErrorResponse(BaseModel):
    """Error response."""

    detail: str
    error_code: str | None = None
