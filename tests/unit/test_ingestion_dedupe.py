"""Tests for idempotent re-ingestion (source-level dedupe)."""

from langchain_core.documents import Document

from energy_rag.ingestion.service import _fresh_documents


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
