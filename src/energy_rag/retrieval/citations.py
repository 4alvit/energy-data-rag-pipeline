"""Citation extraction and formatting for RAG responses."""

import re
from typing import Any

from langchain_core.documents import Document

CITATION_PATTERN = re.compile(r"\[doc_(\d+)\]")


def extract_citations(answer: str, citation_map: dict[str, Document]) -> tuple[str, list[dict]]:
    """
    Extract [doc_N] citations from answer and return formatted sources.

    Returns:
        Tuple of (cleaned_answer, sources_list)
    """
    # Find all citation references
    matches = CITATION_PATTERN.findall(answer)
    cited_indices = {int(m) for m in matches}

    # Build sources list
    sources = []
    for idx in sorted(cited_indices):
        key = f"doc_{idx}"
        if key in citation_map:
            doc = citation_map[key]
            sources.append(format_source(doc, idx))

    # Clean answer - remove citation markers for cleaner output
    # Keep them but could remove: cleaned_answer = CITATION_PATTERN.sub("", answer)
    cleaned_answer = answer

    return cleaned_answer, sources


def format_source(doc: Document, index: int) -> dict[str, Any]:
    """Format a document as a source citation."""
    metadata = doc.metadata

    return {
        "index": index,
        "content": doc.page_content[:500] + ("..." if len(doc.page_content) > 500 else ""),
        "metadata": {
            "product": metadata.get("product"),
            "doc_type": metadata.get("doc_type"),
            "section_title": metadata.get("section_title"),
            "page_number": metadata.get("page_number"),
            "title": metadata.get("title"),
            "source": metadata.get("source"),
            "url": metadata.get("url"),
            "author": metadata.get("author"),
            "chunk_type": metadata.get("chunk_type"),
        },
    }


def format_citations(answer: str, sources: list[dict]) -> str:
    """Format citations as a references section appended to answer."""
    if not sources:
        return answer

    ref_lines = ["\n\n**Sources:**"]
    for src in sources:
        meta = src["metadata"]
        parts = []

        if meta.get("title"):
            parts.append(f"*{meta['title']}*")
        if meta.get("product"):
            parts.append(f"Product: {meta['product']}")
        if meta.get("section_title"):
            parts.append(f"Section: {meta['section_title']}")
        if meta.get("page_number"):
            parts.append(f"Page: {meta['page_number']}")
        if meta.get("url"):
            parts.append(f"URL: {meta['url']}")
        elif meta.get("source"):
            parts.append(f"Source: {meta['source']}")

        ref_lines.append(f"[{src['index']}] {' | '.join(parts)}")

    return answer + "\n".join(ref_lines)
