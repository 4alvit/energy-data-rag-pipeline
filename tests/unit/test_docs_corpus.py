"""Unit tests for the docs corpus exporter."""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPORTER = REPO_ROOT / "scripts" / "export_docs_corpus.py"
CORPUS = REPO_ROOT / "docs-corpus" / "corpus.json"


def test_corpus_is_fresh_and_loadable():
    """Corpus must exist, parse, and match current docs."""
    assert CORPUS.exists(), "docs-corpus/corpus.json missing - run the exporter"

    records = json.loads(CORPUS.read_text(encoding="utf-8"))

    # Regenerate in-memory and compare counts to catch stale artifacts.
    result = subprocess.run(
        [sys.executable, str(EXPORTER)],
        capture_output=True,
        text=True,
        check=True,
    )
    fresh = json.loads(CORPUS.read_text(encoding="utf-8"))
    assert len(fresh) == len(records)
    assert f"{len(fresh)} records" in result.stdout

    for record in fresh:
        assert record["title"], "every record needs a title"
        assert record["body"].strip()
        assert record["url"].startswith("https://github.com/4alvit/energy-data-rag-pipeline/blob/")
        assert "project-docs" in record["tags"]


def test_split_sections_hierarchies():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from export_docs_corpus import split_sections

    md = "# Title\n\nintro\n\n## Alpha\n\nalpha body\n\n### Deep\n\ndeep body\n\n## Beta\n\nbeta body\n"
    sections = split_sections(md)

    by_heading = dict(sections)
    assert by_heading["Title"] == "intro"
    assert by_heading["Title > Alpha"] == "alpha body"
    assert by_heading["Title > Alpha > Deep"] == "deep body"
    assert by_heading["Title > Beta"] == "beta body"
