"""Exercise startup and HTTP routes without models, a database, or network access."""

import os
import sys
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document

from energy_rag.api.routes import query
from energy_rag.config import Settings
from energy_rag.retrieval import chain, factory

main = import_module("energy_rag.api.main")


@pytest.fixture
def components(monkeypatch):
    """Keep real factory and route logic while replacing external resources."""
    config = Settings(
        _env_file=None,
        strict_local_profile=False,
        llm_provider="ollama",
        ollama_base_url="http://localhost:11434",
        similarity_threshold=0.3,
    )
    document = Document(page_content="Battery voltage is 48 V.", metadata={"product": "Quattro"})
    vector_store = SimpleNamespace(
        asimilarity_search=AsyncMock(return_value=[document]),
        asimilarity_search_with_score=AsyncMock(return_value=[(document, 0.1)]),
    )
    llm = SimpleNamespace(ainvoke=AsyncMock(return_value="Battery voltage is 48 V [doc_1]."))
    constructor = MagicMock(return_value=llm)
    monkeypatch.setitem(
        sys.modules,
        "langchain_community.llms.ollama",
        SimpleNamespace(Ollama=constructor),
    )
    monkeypatch.setattr(main, "settings", config)
    monkeypatch.setattr(factory, "settings", config)
    monkeypatch.setattr(chain, "settings", config)
    monkeypatch.setattr(query, "settings", config)
    monkeypatch.setattr(factory, "_llm", None)
    monkeypatch.setattr(factory, "_embeddings", object())
    monkeypatch.setattr(factory, "_vector_store", vector_store)
    # Stale route state must be replaced even when this startup has no LLM.
    monkeypatch.setattr(query, "_llm", object())
    monkeypatch.setattr(query, "_vector_store", object())
    llm_factory = MagicMock(wraps=factory.get_llm)
    embeddings_factory = MagicMock(wraps=factory.get_embeddings)
    vector_factory = MagicMock(wraps=factory.get_vector_store)
    init_database = AsyncMock()
    ensure_extension = AsyncMock()
    monkeypatch.setattr(main, "get_llm", llm_factory)
    monkeypatch.setattr(main, "get_embeddings", embeddings_factory)
    monkeypatch.setattr(main, "get_vector_store", vector_factory)
    monkeypatch.setattr(main, "init_database", init_database)
    monkeypatch.setattr(main, "ensure_vector_extension", ensure_extension)
    return SimpleNamespace(
        config=config,
        vector_store=vector_store,
        llm=llm,
        constructor=constructor,
        llm_factory=llm_factory,
        embeddings_factory=embeddings_factory,
        vector_factory=vector_factory,
        init_database=init_database,
        ensure_extension=ensure_extension,
    )


@pytest.mark.parametrize(
    "failure",
    [
        ImportError("Optional provider package unavailable"),
        RuntimeError("Provider initialization failed"),
        ValueError("Provider model configuration unavailable"),
    ],
    ids=["missing-provider", "provider-runtime-error", "provider-value-error"],
)
def test_unavailable_llm_keeps_retrieval_available(components, failure):
    components.constructor.side_effect = failure
    with TestClient(main.create_app()) as client:
        components.llm_factory.assert_called_once_with()
        components.constructor.assert_called_once()
        components.init_database.assert_awaited_once()
        components.ensure_extension.assert_awaited_once()
        assert query._llm is None
        assert query._vector_store is components.vector_store

        generation = client.post("/query", json={"query": "Battery voltage?"})
        assert generation.status_code == 503
        retrieval = client.post(
            "/query/search",
            json={"query": "Battery voltage?", "top_k": 3, "filters": {"product": "Quattro"}},
        )
        assert retrieval.status_code == 200, retrieval.text
        assert retrieval.json()["results"] == [
            {
                "index": 1,
                "content": "Battery voltage is 48 V.",
                "metadata": {"product": "Quattro"},
            }
        ]
        components.vector_store.asimilarity_search.assert_awaited_once_with(
            "Battery voltage?", k=3, filter={"product": "Quattro"}
        )
        components.vector_store.asimilarity_search_with_score.assert_not_awaited()
        components.llm.ainvoke.assert_not_awaited()
        components.llm_factory.assert_called_once_with()


def test_available_llm_is_initialized_once_and_generates(components):
    with TestClient(main.create_app()) as client:
        components.llm_factory.assert_called_once_with()
        components.constructor.assert_called_once()
        components.embeddings_factory.assert_called_once_with()
        components.vector_factory.assert_called_once_with()
        assert query._llm is components.llm
        assert query._vector_store is components.vector_store
        response = client.post("/query", json={"query": "Battery voltage?"})
        assert response.status_code == 200, response.text
        assert "Battery voltage is 48 V" in response.json()["answer"]
        assert response.json()["sources"][0]["content"] == "Battery voltage is 48 V."
        components.llm.ainvoke.assert_awaited_once()


@pytest.mark.parametrize(
    ("violation", "message"),
    [
        ("remote-ollama", "Ollama HTTP on loopback"),
        ("outbound-proxy", "proxy variables unset"),
    ],
)
def test_strict_policy_failure_aborts_before_resource_initialization(
    components, monkeypatch, tmp_path, violation, message
):
    for name in list(os.environ):
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
    strict_config = Settings(
        _env_file=None,
        strict_local_profile=True,
        embedding_model=str(tmp_path),
        api_host="127.0.0.1",
        llm_provider="ollama",
        ollama_base_url="http://localhost:11434",
        database_url="postgresql+asyncpg://rag:testpass@localhost/test",
        enable_rerank=False,
    )
    monkeypatch.setattr(main, "settings", strict_config)
    monkeypatch.setattr(factory, "settings", strict_config)
    # Settings were valid when loaded; startup must recheck the actual policy.
    if violation == "remote-ollama":
        strict_config.ollama_base_url = "http://192.0.2.1:11434"
    else:
        monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example.invalid:3128")
    with pytest.raises(ValueError, match=message), TestClient(main.create_app()):
        pytest.fail("Strict deployment policy must prevent startup")
    components.constructor.assert_not_called()
    components.init_database.assert_not_awaited()
    components.ensure_extension.assert_not_awaited()
    components.embeddings_factory.assert_not_called()
    components.vector_factory.assert_not_called()
