"""The strict local profile cannot silently select an unmanaged network route."""

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from energy_rag.config import Settings
from energy_rag.deployment_policy import (
    database_options,
    local_model_options,
    validate_environment,
    validate_llm,
)


@pytest.fixture
def strict_environment(monkeypatch):
    for name in list(__import__("os").environ):
        if name.upper() in {
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "LANGCHAIN_TRACING",
            "LANGCHAIN_TRACING_V2",
            "LANGSMITH_TRACING",
        }:
            monkeypatch.delenv(name)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    constants = sys.modules.get("huggingface_hub.constants")
    if constants is not None:
        monkeypatch.setattr(constants, "HF_HUB_OFFLINE", True)


def test_strict_settings_require_local_models_and_api(tmp_path, strict_environment):
    config = Settings(
        _env_file=None,
        strict_local_profile=True,
        embedding_model=str(tmp_path),
        api_host="127.0.0.1",
    )
    assert config.strict_local_profile
    with pytest.raises(ValueError, match="model directory"):
        Settings(_env_file=None, strict_local_profile=True, api_host="127.0.0.1")
    with pytest.raises(ValueError, match="API_HOST"):
        Settings(_env_file=None, strict_local_profile=True, embedding_model=str(tmp_path))


@pytest.mark.parametrize(
    "provider,url",
    [
        ("openai", "http://localhost:11434"),
        ("anthropic", "http://localhost:11434"),
        ("ollama", "https://localhost:11434"),
        ("ollama", "http://192.0.2.1:11434"),
        ("ollama", "http://user:secret@localhost:11434"),
    ],
)
def test_rejects_unmanaged_llm_transport(provider, url, strict_environment):
    with pytest.raises(ValueError, match="Ollama HTTP on loopback"):
        validate_llm(provider, url, True)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://u:p@example.com/db",
        "postgresql+asyncpg://u:p@localhost/db?ssl=require",
        "postgresql+asyncpg://u:p@localhost/db?host=example.com",
        "postgresql://u:p@localhost/db",
    ],
)
def test_rejects_database_overrides(url, strict_environment):
    with pytest.raises(ValueError, match="loopback asyncpg"):
        database_options(url, True)


@pytest.mark.parametrize(
    "name,value",
    [
        ("https_proxy", "http://localhost:3128"),
        ("ALL_PROXY", "socks5://localhost:1080"),
        ("LANGSMITH_TRACING", "true"),
        ("HF_HUB_OFFLINE", "0"),
    ],
)
def test_rejects_outbound_environment(name, value, strict_environment, monkeypatch):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        validate_environment()


def test_rejects_already_online_hub(strict_environment, monkeypatch):
    monkeypatch.setitem(
        sys.modules, "huggingface_hub.constants", SimpleNamespace(HF_HUB_OFFLINE=False)
    )
    with pytest.raises(ValueError, match="Restart"):
        validate_environment()


def test_local_model_does_not_allow_download_fallback(tmp_path, strict_environment):
    assert local_model_options(str(tmp_path), True) == {"local_files_only": True}
    with pytest.raises(ValueError, match="model directory"):
        local_model_options("vendor/model-on-hub", True)


def test_factory_wires_local_only_embeddings(tmp_path, strict_environment, monkeypatch):
    from energy_rag.retrieval import factory

    constructor = MagicMock()
    monkeypatch.setitem(
        sys.modules, "langchain_huggingface", SimpleNamespace(HuggingFaceEmbeddings=constructor)
    )
    monkeypatch.setattr(factory, "_embeddings", None)
    monkeypatch.setattr(factory.settings, "strict_local_profile", True)
    monkeypatch.setattr(factory.settings, "embedding_model", str(tmp_path))
    factory.get_embeddings()
    assert constructor.call_args.kwargs["model_kwargs"]["local_files_only"] is True


def test_reranker_wires_local_only_model(tmp_path, strict_environment, monkeypatch):
    from energy_rag.retrieval import rerank

    constructor = MagicMock()
    monkeypatch.setitem(
        sys.modules, "sentence_transformers", SimpleNamespace(CrossEncoder=constructor)
    )
    monkeypatch.setattr(rerank.settings, "strict_local_profile", True)
    rerank.Reranker(str(tmp_path))._load_model()
    assert constructor.call_args.kwargs["local_files_only"] is True


def test_database_and_vectorstore_disable_opportunistic_tls(strict_environment, monkeypatch):
    from energy_rag.retrieval import factory
    from energy_rag.storage import pgvector

    constructor = MagicMock()
    monkeypatch.setattr(pgvector, "create_async_engine", constructor)
    monkeypatch.setattr(pgvector.settings, "strict_local_profile", True)
    assert (
        pgvector.PgVectorDatabase("postgresql+asyncpg://u:p@localhost/db").engine
        is constructor.return_value
    )
    assert constructor.call_args.kwargs["connect_args"] == {"ssl": False}
    vector_constructor = MagicMock()
    monkeypatch.setitem(
        sys.modules, "langchain_postgres", SimpleNamespace(PGVector=vector_constructor)
    )
    monkeypatch.setattr(factory, "_vector_store", None)
    monkeypatch.setattr(factory, "get_embeddings", MagicMock())
    factory.get_vector_store()
    assert vector_constructor.call_args.kwargs["engine_args"] == {"connect_args": {"ssl": False}}


async def test_extension_helper_disables_opportunistic_tls(strict_environment, monkeypatch):
    from energy_rag.storage import pgvector

    engine = MagicMock()
    engine.begin.return_value.__aenter__.return_value.execute = AsyncMock()
    engine.dispose = AsyncMock()
    constructor = MagicMock(return_value=engine)
    monkeypatch.setattr(pgvector, "create_async_engine", constructor)
    monkeypatch.setattr(pgvector.settings, "strict_local_profile", True)
    assert await pgvector.ensure_vector_extension("postgresql+asyncpg://u:p@localhost/db")
    assert constructor.call_args.kwargs["connect_args"] == {"ssl": False}
