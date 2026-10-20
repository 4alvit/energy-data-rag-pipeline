"""Unit tests for the docs corpus exporter."""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS = REPO_ROOT / "docs-corpus" / "corpus.json"


def test_corpus_is_fresh_and_loadable(tmp_path, monkeypatch, capsys):
    """Corpus must exist, parse, and match current docs."""
    assert CORPUS.exists(), "docs-corpus/corpus.json missing - run the exporter"
    original = CORPUS.read_bytes()
    original_readme = CORPUS.with_name("README.md").read_bytes()
    records = json.loads(original)

    monkeypatch.syspath_prepend(str(REPO_ROOT / "scripts"))
    import export_docs_corpus

    monkeypatch.setattr(export_docs_corpus, "OUT_DIR", tmp_path)
    assert export_docs_corpus.main() == 0
    fresh = json.loads((tmp_path / "corpus.json").read_text(encoding="utf-8"))
    # Only generation timestamps may differ; equal counts can hide stale content.
    assert [
        {key: value for key, value in record.items() if key != "created_at"} for record in fresh
    ] == [
        {key: value for key, value in record.items() if key != "created_at"} for record in records
    ]
    assert f"{len(fresh)} records" in capsys.readouterr().out
    assert CORPUS.read_bytes() == original
    assert CORPUS.with_name("README.md").read_bytes() == original_readme

    for record in fresh:
        assert record["title"], "every record needs a title"
        assert record["body"].strip()
        assert record["url"].startswith("https://github.com/4alvit/energy-data-rag-pipeline/blob/")
        assert "project-docs" in record["tags"]


def test_split_sections_hierarchies(monkeypatch):
    monkeypatch.syspath_prepend(str(REPO_ROOT / "scripts"))
    from export_docs_corpus import split_sections

    md = "# Title\n\nintro\n\n## Alpha\n\nalpha body\n\n### Deep\n\ndeep body\n\n## Beta\n\nbeta body\n"
    sections = split_sections(md)

    by_heading = dict(sections)
    assert by_heading["Title"] == "intro"
    assert by_heading["Title > Alpha"] == "alpha body"
    assert by_heading["Title > Alpha > Deep"] == "deep body"
    assert by_heading["Title > Beta"] == "beta body"
