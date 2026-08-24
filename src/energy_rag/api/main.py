"""FastAPI application for Energy RAG Pipeline."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

# Structured logging
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from energy_rag import __version__
from energy_rag.api.routes import health, ingest, query
from energy_rag.api.schemas import ErrorResponse
from energy_rag.config import settings
from energy_rag.retrieval.factory import get_embeddings, get_llm, get_vector_store
from energy_rag.storage.pgvector import ensure_vector_extension, init_database

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logging.basicConfig(level=settings.log_level)

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    logger.info("Starting Energy RAG Pipeline")

    # Initialize database (audit/ingestion_runs schema + pgvector extension)
    await init_database()
    await ensure_vector_extension()

    # Initialize components (embeddings model download happens here)
    get_embeddings()
    get_vector_store()
    try:
        get_llm()
    except Exception as exc:  # LLM is optional until first query
        logger.warning("LLM unavailable at startup: %s", exc)

    # Set dependencies for query route
    query.set_dependencies(get_vector_store(), get_llm())

    logger.info("Energy RAG Pipeline started")

    yield

    # Cleanup
    logger.info("Shutting down Energy RAG Pipeline")


def create_app() -> FastAPI:
    """Create FastAPI application."""
    app = FastAPI(
        title="Energy RAG Pipeline",
        description="RAG pipeline for Victron Energy documentation",
        version=__version__,
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routes
    app.include_router(health.router)
    app.include_router(query.router)
    app.include_router(ingest.router)

    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        logger.exception("Unhandled exception: %s", exc)
        return ErrorResponse(
            detail=str(exc),
            error_code="INTERNAL_ERROR",
        ).model_dump()

    return app


app = create_app()


def main():
    """Entry point for uvicorn."""
    import uvicorn

    uvicorn.run(
        "energy_rag.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        workers=settings.api_workers,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
