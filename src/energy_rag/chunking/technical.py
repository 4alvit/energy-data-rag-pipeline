"""Technical documentation chunking strategies."""

import logging
from typing import Any, ClassVar

from langchain_core.documents import Document
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from energy_rag.config import settings

logger = logging.getLogger(__name__)


# Headers to split on for technical documentation
MARKDOWN_HEADERS = [
    ("#", "h1"),
    ("##", "h2"),
    ("###", "h3"),
    ("####", "h4"),
]


class TechnicalChunker:
    """Chunking strategy optimized for technical documentation."""

    def __init__(
        self,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ):
        self.chunk_size = chunk_size or settings.chunk_size
        self.chunk_overlap = chunk_overlap or settings.chunk_overlap

        # Markdown header splitter for structured docs
        self.header_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=MARKDOWN_HEADERS,
            strip_headers=False,
        )

        # Fallback recursive splitter for unstructured text
        self.recursive_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    def chunk_documents(self, documents: list[Document]) -> list[Document]:
        """Chunk documents using markdown-aware splitting with fallback."""
        chunked = []

        for doc in documents:
            # Try markdown header splitting first
            try:
                header_chunks = self.header_splitter.split_text(doc.page_content)

                if len(header_chunks) > 1:
                    # Successfully split by headers
                    for chunk in header_chunks:
                        chunked.append(self._create_chunk(doc, chunk))
                    continue
            except Exception as e:
                logger.debug("Header splitting failed for doc: %s", e)

            # Fallback to recursive splitting
            recursive_chunks = self.recursive_splitter.split_text(doc.page_content)
            for chunk_text in recursive_chunks:
                chunked.append(
                    Document(
                        page_content=chunk_text,
                        metadata={
                            **doc.metadata,
                            "chunk_method": "recursive",
                            "chunk_size": len(chunk_text),
                        },
                    )
                )

        logger.info("Chunked %d documents into %d chunks", len(documents), len(chunked))
        return chunked

    def _create_chunk(self, original_doc: Document, chunk: Document) -> Document:
        """Create a new chunk document with merged metadata."""
        # Extract header metadata from chunk
        header_metadata = {}
        for key, value in chunk.metadata.items():
            if key in ("h1", "h2", "h3", "h4"):
                header_metadata[key] = value

        # Build section title from headers
        section_parts = []
        for h in ["h1", "h2", "h3", "h4"]:
            if header_metadata.get(h):
                section_parts.append(header_metadata[h])

        merged_metadata = {
            **original_doc.metadata,
            **header_metadata,
            "chunk_method": "markdown_header",
            "section_title": " > ".join(section_parts) if section_parts else "",
            "chunk_size": len(chunk.page_content),
        }

        return Document(page_content=chunk.page_content, metadata=merged_metadata)


class _SplitterAdapter:
    """Adapt a LangChain text splitter to the chunk_documents contract.

    The ingestion pipeline calls ``chunker.chunk_documents(docs)`` for every
    strategy; raw LangChain splitters only expose ``split_documents``.
    """

    def __init__(self, splitter: Any) -> None:
        self._splitter = splitter

    def chunk_documents(self, documents: list[Document]) -> list[Document]:
        if hasattr(self._splitter, "split_documents"):
            return list(self._splitter.split_documents(documents))
        # Text-only splitters (e.g. MarkdownHeaderTextSplitter): keep metadata.
        chunks: list[Document] = []
        for doc in documents:
            chunks.extend(self._splitter.split_text(doc.page_content))
        return chunks


class ChunkingStrategy:
    """Factory for different chunking strategies."""

    STRATEGIES: ClassVar[dict[str, object]] = {
        "technical": TechnicalChunker,
        "markdown": MarkdownHeaderTextSplitter,
        "recursive": RecursiveCharacterTextSplitter,
        "fixed": "CharacterTextSplitter",
    }

    @classmethod
    def create(cls, strategy: str = "technical", **kwargs) -> Any:
        """Create chunker by strategy name."""
        if strategy == "technical":
            return TechnicalChunker(**kwargs)

        if strategy == "markdown":
            return _SplitterAdapter(
                MarkdownHeaderTextSplitter(
                    headers_to_split_on=MARKDOWN_HEADERS,
                    strip_headers=kwargs.get("strip_headers", False),
                )
            )

        if strategy == "recursive":
            return _SplitterAdapter(
                RecursiveCharacterTextSplitter(
                    chunk_size=kwargs.get("chunk_size", settings.chunk_size),
                    chunk_overlap=kwargs.get("chunk_overlap", settings.chunk_overlap),
                    length_function=len,
                )
            )

        if strategy == "fixed":
            from langchain_text_splitters import CharacterTextSplitter

            return _SplitterAdapter(
                CharacterTextSplitter(
                    chunk_size=kwargs.get("chunk_size", settings.chunk_size),
                    chunk_overlap=kwargs.get("chunk_overlap", settings.chunk_overlap),
                )
            )

        raise ValueError(f"Unknown chunking strategy: {strategy}")

    @classmethod
    def get_available(cls) -> list[str]:
        """Get list of available strategies."""
        return list(cls.STRATEGIES.keys())


def create_chunker(strategy: str = "technical", **kwargs) -> Any:
    """Convenience function to create a chunker."""
    return ChunkingStrategy.create(strategy, **kwargs)
