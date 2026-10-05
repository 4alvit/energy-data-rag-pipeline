"""Unit tests for chunking strategies."""

import logging

import pytest
from langchain_core.documents import Document

from energy_rag.chunking import create_chunker


def test_technical_chunker_basic():
    """Test technical chunker with markdown headers."""
    chunker = create_chunker("technical", chunk_size=500, chunk_overlap=50)

    doc = Document(
        page_content="# Header 1\n\nContent 1\n\n## Header 2\n\nContent 2",
        metadata={"source": "test.md"},
    )

    chunks = chunker.chunk_documents([doc])

    assert len(chunks) >= 2
    assert chunks[0].metadata.get("h1") == "Header 1"
    assert chunks[1].metadata.get("h2") == "Header 2"


def test_technical_chunker_no_headers():
    """Test technical chunker falls back to recursive splitting."""
    chunker = create_chunker("technical", chunk_size=100, chunk_overlap=20)

    doc = Document(
        page_content="This is a long text without any markdown headers. " * 10,
        metadata={"source": "test.txt"},
    )

    chunks = chunker.chunk_documents([doc])

    assert len(chunks) > 1
    assert all(c.metadata.get("chunk_method") == "recursive" for c in chunks)


def test_recursive_chunker():
    """Test recursive chunking strategy."""
    chunker = create_chunker("recursive", chunk_size=100, chunk_overlap=20)

    doc = Document(
        page_content="Paragraph 1.\n\nParagraph 2.\n\nParagraph 3.",
        metadata={"source": "test.txt"},
    )

    chunks = chunker.chunk_documents([doc])

    assert len(chunks) >= 1
    assert all(c.metadata.get("source") == "test.txt" for c in chunks)


def test_markdown_chunker():
    """Test markdown header chunking strategy."""
    chunker = create_chunker("markdown")

    doc = Document(
        page_content="# Title\n\n## Section 1\n\nContent 1\n\n## Section 2\n\nContent 2",
        metadata={},
    )

    chunks = chunker.chunk_documents([doc])

    # Splits into sections (not including root title as separate)
    assert len(chunks) == 2  # Section 1 and Section 2
    assert chunks[0].metadata.get("h1") == "Title"
    assert chunks[0].metadata.get("h2") == "Section 1"
    assert chunks[1].metadata.get("h1") == "Title"
    assert chunks[1].metadata.get("h2") == "Section 2"


@pytest.mark.parametrize("strategy", ["technical", "markdown", "recursive", "fixed"])
def test_chunkers_accept_single_pass_documents_and_preserve_sources(strategy):
    """Real loader iterators must keep provenance needed by citations and dedupe."""
    documents = [
        Document(
            page_content=f"# Manual {index}\n\n## First\n\nFirst instructions.\n\n"
            "## Second\n\nSecond instructions.",
            metadata={"source": f"manual-{index}.json", "url": f"https://example.org/{index}"},
        )
        for index in range(2)
    ]
    originals = [dict(doc.metadata) for doc in documents]
    consumed = []

    def stream():
        for doc in documents:
            consumed.append(doc.metadata["source"])
            yield doc

    chunks = create_chunker(strategy).chunk_documents(stream())

    assert consumed == ["manual-0.json", "manual-1.json"]
    assert {chunk.metadata["source"] for chunk in chunks} == set(consumed)
    for index in range(2):
        source_chunks = [c for c in chunks if c.metadata["source"] == f"manual-{index}.json"]
        assert source_chunks
        assert all(c.metadata["url"] == f"https://example.org/{index}" for c in source_chunks)
        assert "First instructions." in "\n".join(c.page_content for c in source_chunks)
        assert "Second instructions." in "\n".join(c.page_content for c in source_chunks)
    assert [doc.metadata for doc in documents] == originals


def test_technical_chunker_counts_consumed_generator_documents(caplog):
    """Logging counts inputs during traversal without asking the iterator for len()."""
    with caplog.at_level(logging.INFO):
        chunks = create_chunker("technical").chunk_documents(
            Document(page_content=f"Document {i}") for i in range(2)
        )
    assert len(chunks) == 2
    assert "Chunked 2 documents into 2 chunks" in caplog.text


def test_technical_chunker_empty_generator(caplog):
    """An empty loader is valid and is reported as zero documents."""
    with caplog.at_level(logging.INFO):
        assert create_chunker("technical").chunk_documents(iter(())) == []
    assert "Chunked 0 documents into 0 chunks" in caplog.text
