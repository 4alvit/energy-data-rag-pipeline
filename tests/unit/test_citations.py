"""Unit tests for citation extraction."""

from langchain_core.documents import Document

from energy_rag.retrieval.citations import (
    extract_citations,
    format_citations,
    format_source,
)


def _doc_map() -> dict[str, Document]:
    return {
        "doc_1": Document(
            page_content="ESS assistant uses grid zero to prevent feed-in.",
            metadata={
                "title": "MultiPlus-II Manual",
                "product": "MultiPlus-II",
                "section_title": "ESS settings",
                "page_number": 42,
                "url": "https://example.com/manual",
            },
        ),
        "doc_2": Document(
            page_content="VE.Direct protocol transmits telemetry.",
            metadata={"title": "VEDirect protocol", "source": "forum"},
        ),
    }


def test_extract_citations_finds_cited_docs():
    answer = "Grid zero prevents export [doc_1] and VE.Direct streams data [doc_2]."
    cleaned, sources = extract_citations(answer, _doc_map())

    assert [s["index"] for s in sources] == [1, 2]
    assert sources[0]["metadata"]["product"] == "MultiPlus-II"
    assert sources[0]["metadata"]["page_number"] == 42
    assert cleaned == answer


def test_extract_citations_ignores_unknown_indices():
    _, sources = extract_citations("Nothing to see [doc_9].", _doc_map())
    assert sources == []


def test_extract_citations_no_markers():
    _, sources = extract_citations("Plain answer.", _doc_map())
    assert sources == []


def test_format_source_truncates_long_content():
    doc = Document(page_content="x" * 1000, metadata={})
    src = format_source(doc, 3)
    assert len(src["content"]) == 503  # 500 + ellipsis
    assert src["index"] == 3


def test_format_citations_appends_references():
    doc = Document(
        page_content="body",
        metadata={"title": "T", "url": "https://example.com"},
    )
    sources = [format_source(doc, 1)]
    out = format_citations("Answer text.", sources)
    assert "**Sources:**" in out
    assert "[1]" in out
    assert "https://example.com" in out


def test_format_citations_without_sources_is_identity():
    assert format_citations("Answer.", []) == "Answer."
