"""Exercise real document loaders through the service's file and directory paths."""

import json
from pathlib import Path

import fitz
import pytest

from energy_rag.chunking import create_chunker
from energy_rag.ingestion.pipeline import create_ingestion_pipeline
from energy_rag.ingestion.service import _load_documents


def write_json(path: Path) -> None:
    """Write a two-section source with a canonical citation URL."""
    path.write_text(
        json.dumps(
            {
                "title": "Technical manual",
                "body": "## Signals\n\nSignal instructions.\n\n## Modes\n\nMode instructions.",
                "url": "https://example.org/technical-manual",
            }
        )
    )


@pytest.mark.parametrize("strategy", ["technical", "markdown", "recursive", "fixed"])
def test_file_and_directory_use_same_real_chunker(tmp_path, strategy):
    """Selecting one JSON file or its directory must produce identical chunks."""
    source = tmp_path / "manual.json"
    write_json(source)
    pipeline = create_ingestion_pipeline(create_chunker(strategy, chunk_size=50, chunk_overlap=10))

    direct = _load_documents(pipeline, "forum_json", source, recursive=True)
    directory = _load_documents(pipeline, "forum_json", tmp_path, recursive=True)

    assert len(direct) > 1
    assert direct == directory
    assert all(c.metadata["source"] == str(source) for c in direct)
    assert all(c.metadata["url"] == "https://example.org/technical-manual" for c in direct)


@pytest.mark.parametrize("source_type,suffix", [("forum_json", ".json"), ("forum_html", ".html")])
def test_nonrecursive_directory_does_not_load_nested_files(tmp_path, source_type, suffix):
    """Honor the public recursive flag for forum sources as well as PDFs."""
    nested = tmp_path / "nested"
    nested.mkdir()
    source = nested / ("manual" + suffix)
    if source_type == "forum_json":
        write_json(source)
    else:
        source.write_text("<article><h1>Manual</h1><p>Signal instructions.</p></article>")
    pipeline = create_ingestion_pipeline(create_chunker("technical"))
    assert _load_documents(pipeline, source_type, tmp_path, recursive=False) == []
    assert _load_documents(pipeline, source_type, tmp_path, recursive=True)


def test_invalid_directory_document_propagates_original_error(tmp_path):
    """A malformed source must not become a successful zero-chunk ingestion."""
    (tmp_path / "broken.json").write_text("not JSON")
    pipeline = create_ingestion_pipeline(create_chunker("technical"))
    with pytest.raises(json.JSONDecodeError):
        _load_documents(pipeline, "forum_json", tmp_path, recursive=True)


@pytest.mark.parametrize("source_type", ["pdf", "forum_html"])
def test_other_file_types_match_directory_chunking(tmp_path, source_type):
    """Real PDF and HTML loaders share the same chunking contract as JSON."""
    content = "Signal instructions and troubleshooting steps. " * 10
    if source_type == "pdf":
        source = tmp_path / "manual.pdf"
        with fitz.open() as document:
            page = document.new_page()
            page.insert_textbox(fitz.Rect(40, 40, 500, 700), content)
            document.save(source)
    else:
        source = tmp_path / "manual.html"
        source.write_text(f"<article><h1>Manual</h1><p>{content}</p></article>")
    pipeline = create_ingestion_pipeline(
        create_chunker("technical", chunk_size=100, chunk_overlap=20)
    )
    direct = _load_documents(pipeline, source_type, source, recursive=True)
    assert len(direct) > 1
    assert direct == _load_documents(pipeline, source_type, tmp_path, recursive=True)
    assert all(c.metadata["source"] == str(source) for c in direct)


def test_invalid_community_export_propagates_original_error(tmp_path):
    """The community export wrapper must not silently hide a failed JSON file."""
    (tmp_path / "broken.json").write_text("not JSON")
    pipeline = create_ingestion_pipeline(create_chunker("technical"))
    with pytest.raises(json.JSONDecodeError):
        list(pipeline.ingest_victron_community_export(tmp_path))
