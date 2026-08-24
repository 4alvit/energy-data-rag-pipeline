"""Singleton factories for embeddings, LLM and vector store."""

import logging

from energy_rag.config import settings

logger = logging.getLogger(__name__)

# Global instances
_vector_store = None
_embeddings = None
_llm = None


def get_embeddings():
    """Get or create embeddings model."""
    global _embeddings
    if _embeddings is None:
        from langchain_huggingface import HuggingFaceEmbeddings

        _embeddings = HuggingFaceEmbeddings(
            model_name=settings.embedding_model,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        logger.info("Initialized embeddings", extra={"model": settings.embedding_model})
    return _embeddings


def get_llm():
    """Get or create LLM based on provider."""
    global _llm
    if _llm is None:
        if settings.llm_provider == "ollama":
            from langchain_community.llms.ollama import Ollama

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
                base_url=settings.llm_base_url or None,
                temperature=0.1,
            )
        elif settings.llm_provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            _llm = ChatAnthropic(
                model=settings.llm_model,
                api_key=settings.anthropic_api_key,
                base_url=settings.llm_base_url or None,
                temperature=0.1,
            )
        else:
            raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")

        logger.info(
            "Initialized LLM",
            extra={"provider": settings.llm_provider, "model": settings.llm_model},
        )
    return _llm


def get_vector_store():
    """Get or create the pgvector-backed LangChain vector store."""
    global _vector_store
    if _vector_store is None:
        # langchain_postgres.PGVector manages its own schema (langchain_pg_*).
        # async_mode=True wires an async SQLAlchemy engine; only *a*-prefixed
        # methods are callable on this instance.
        from langchain_postgres import PGVector

        _vector_store = PGVector(
            embeddings=get_embeddings(),
            collection_name="energy_docs",
            connection=settings.database_url,
            use_jsonb=True,
            pre_delete_collection=False,
            async_mode=True,
            # We ensure the extension ourselves (see storage.pgvector) because
            # langchain_postgres's async path breaks on multi-statement SQL.
            create_extension=False,
        )
        logger.info("Initialized PGVector store")
    return _vector_store
