"""FastAPI application for Energy RAG Pipeline."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

# Structured logging
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langchain_community.vectorstores import PGVector
from langchain_huggingface import HuggingFaceEmbeddings

from energy_rag.api.routes import health, ingest, query
from energy_rag.api.schemas import ErrorResponse
from energy_rag.config import settings
from energy_rag.storage.pgvector import init_database

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

# Global instances
_vector_store = None
_embeddings = None
_llm = None


def get_embeddings():
    """Get or create embeddings model."""
    global _embeddings
    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(
            model_name=settings.embedding_model,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        logger.info("Initialized embeddings", model=settings.embedding_model)
    return _embeddings


def get_llm():
    """Get or create LLM based on provider."""
    global _llm
    if _llm is None:
        if settings.llm_provider == "ollama":
            from langchain_community.llms import Ollama
            _llm = Ollama(
                model=settings.llm_model,
                base_url=settings.ollama_base_url,
                temperature=0.1,
            )
        elif settings.llm_provider == "openai":
            from langchain_openai import ChatOpenAI
            _llm = ChatOpenAI(
                model=settings.llm_model,
                api_key=settings.openai_api_key,
                temperature=0.1,
            )
        elif settings.llm_provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            _llm = ChatAnthropic(
                model=settings.llm_model,
                api_key=settings.anthropic_api_key,
                temperature=0.1,
            )
        else:
            raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")

        logger.info("Initialized LLM", provider=settings.llm_provider, model=settings.llm_model)
    return _llm


def get_vector_store():
    """Get or create PGVector store."""
    global _vector_store
    if _vector_store is None:
        embeddings = get_embeddings()
        _vector_store = PGVector(
            embeddings=embeddings,
            collection_name="energy_docs",
            connection=settings.database_url,
            use_jsonb=True,
        )
        logger.info("Initialized PGVector store")
    return _vector_store


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    logger.info("Starting Energy RAG Pipeline")

    # Initialize database
    await init_database()

    # Initialize components
    get_embeddings()
    get_llm()
    get_vector_store()

    # Set dependencies for query route
    query.set_dependencies(_vector_store, _llm)

    logger.info("Energy RAG Pipeline started")

    yield

    # Cleanup
    logger.info("Shutting down Energy RAG Pipeline")


def create_app() -> FastAPI:
    """Create FastAPI application."""
    app = FastAPI(
        title="Energy RAG Pipeline",
        description="RAG pipeline for Victron Energy documentation",
        version="0.1.0",
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