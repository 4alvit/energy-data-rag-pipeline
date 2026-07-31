"""Configuration settings for Energy RAG Pipeline."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://rag:changeme@localhost:5432/energy_rag",
        description="PostgreSQL connection string with pgvector",
    )

    # Embeddings
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="HuggingFace embedding model name",
    )
    embedding_dimension: int = Field(
        default=384,
        description="Embedding vector dimension (must match model)",
    )

    # LLM Provider
    llm_provider: Literal["ollama", "openai", "anthropic"] = Field(
        default="ollama",
        description="LLM provider for generation",
    )
    llm_model: str = Field(
        default="llama3.1:8b",
        description="LLM model name",
    )

    # Ollama
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Ollama API base URL",
    )

    # OpenAI
    openai_api_key: str = Field(
        default="",
        description="OpenAI API key (required if llm_provider=openai)",
    )

    # Anthropic
    anthropic_api_key: str = Field(
        default="",
        description="Anthropic API key (required if llm_provider=anthropic)",
    )

    # Retrieval
    default_top_k: int = Field(
        default=5,
        description="Default number of documents to retrieve",
    )
    similarity_threshold: float = Field(
        default=0.7,
        description="Minimum cosine similarity threshold",
    )
    enable_rerank: bool = Field(
        default=False,
        description="Enable cross-encoder reranking",
    )
    rerank_model: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2",
        description="Cross-encoder model for reranking",
    )

    # Ingestion
    chunk_size: int = Field(
        default=1000,
        description="Default chunk size for text splitting",
    )
    chunk_overlap: int = Field(
        default=200,
        description="Overlap between chunks",
    )

    # API
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8000, description="API port")
    api_workers: int = Field(default=1, description="Number of Uvicorn workers")

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()