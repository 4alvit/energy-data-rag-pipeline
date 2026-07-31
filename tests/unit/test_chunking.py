"""Unit tests for chunking strategies."""

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

    # RecursiveCharacterTextSplitter uses create_documents
    chunks = chunker.create_documents([doc.page_content], metadatas=[doc.metadata])

    assert len(chunks) >= 1


def test_markdown_chunker():
    """Test markdown header chunking strategy."""
    chunker = create_chunker("markdown")

    doc = Document(
        page_content="# Title\n\n## Section 1\n\nContent 1\n\n## Section 2\n\nContent 2",
        metadata={},
    )

    # MarkdownHeaderTextSplitter uses split_text
    chunks = chunker.split_text(doc.page_content)

    # Splits into sections (not including root title as separate)
    assert len(chunks) == 2  # Section 1 and Section 2
    assert chunks[0].metadata.get("h1") == "Title"
    assert chunks[0].metadata.get("h2") == "Section 1"
    assert chunks[1].metadata.get("h1") == "Title"
    assert chunks[1].metadata.get("h2") == "Section 2"