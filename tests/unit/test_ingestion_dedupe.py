"""Tests for idempotent re-ingestion (source-level dedupe)."""

from unittest.mock import AsyncMock

import pytest
from langchain_core.documents import Document

from energy_rag.ingestion.service import _fresh_documents, _stored_sources


def test_fresh_documents_filters_already_ingested_sources():
    docs = [
        Document(
            page_content="a", metadata={"source": "/data/manuals/old.pdf", "source_type": "pdf"}
        ),
        Document(
            page_content="b", metadata={"source": "/data/manuals/new.pdf", "source_type": "pdf"}
        ),
        Document(page_content="c", metadata={}),  # no source key -> kept
    ]
    stored = {"/data/manuals/old.pdf"}

    fresh = _fresh_documents(docs, stored)

    assert [d.metadata.get("source") for d in fresh] == ["/data/manuals/new.pdf", None]


def test_fresh_documents_keeps_everything_when_store_empty():
    docs = [Document(page_content="x", metadata={"source": "/data/manuals/m.pdf"})]
    assert _fresh_documents(docs, set()) == docs


async def test_stored_sources_before_first_vector_store_operation():
    """Lazy PGVector initialization means a missing table is an empty index."""
    session = AsyncMock()
    session.scalar.return_value = None
    assert await _stored_sources(session) == set()
    session.execute.assert_not_awaited()


async def test_stored_sources_keeps_existing_source_deduplication():
    """Once the embedding table exists, its nonempty source paths still dedupe."""
    session = AsyncMock()
    session.scalar.return_value = "langchain_pg_embedding"
    session.execute.return_value = [("/data/manual.json",), (None,), ("",)]
    assert await _stored_sources(session) == {"/data/manual.json"}


async def test_stored_sources_does_not_hide_database_errors():
    """Only an absent relation is empty; connection/query failures remain failures."""
    session = AsyncMock()
    session.scalar.side_effect = RuntimeError("database unavailable")
    with pytest.raises(RuntimeError, match="database unavailable"):
        await _stored_sources(session)
