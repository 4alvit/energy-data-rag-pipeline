"""Dependency-free tests for the documentation corpus exporter."""

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS = REPO_ROOT / "docs-corpus" / "corpus.json"
SPEC = importlib.util.spec_from_file_location(
    "docs_corpus_exporter", REPO_ROOT / "scripts/export_docs_corpus.py"
)
EXPORTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORTER)


class DocsCorpusTests(unittest.TestCase):
    def test_corpus_is_fresh_and_loadable(self):
        """Corpus must exist, parse, and match current docs without rewriting inputs."""
        self.assertTrue(CORPUS.exists(), "docs-corpus/corpus.json missing - run the exporter")
        original = CORPUS.read_bytes()
        original_readme = CORPUS.with_name("README.md").read_bytes()
        records = json.loads(original)
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            with patch.object(EXPORTER, "OUT_DIR", destination), redirect_stdout(output):
                self.assertEqual(EXPORTER.main(), 0)
            fresh = json.loads((destination / "corpus.json").read_text(encoding="utf-8"))
        # Only generation timestamps may differ; equal counts can hide stale content.
        self.assertEqual(
            [
                {key: value for key, value in record.items() if key != "created_at"}
                for record in fresh
            ],
            [
                {key: value for key, value in record.items() if key != "created_at"}
                for record in records
            ],
        )
        self.assertIn(f"{len(fresh)} records", output.getvalue())
        self.assertEqual(CORPUS.read_bytes(), original)
        self.assertEqual(CORPUS.with_name("README.md").read_bytes(), original_readme)
        for record in fresh:
            self.assertTrue(record["title"], "every record needs a title")
            self.assertTrue(record["body"].strip())
            self.assertTrue(
                record["url"].startswith("https://github.com/4alvit/energy-data-rag-pipeline/blob/")
            )
            self.assertIn("project-docs", record["tags"])

    def test_split_sections_hierarchies(self):
        md = "# Title\n\nintro\n\n## Alpha\n\nalpha body\n\n### Deep\n\ndeep body\n\n## Beta\n\nbeta body\n"
        by_heading = dict(EXPORTER.split_sections(md))
        self.assertEqual(by_heading["Title"], "intro")
        self.assertEqual(by_heading["Title > Alpha"], "alpha body")
        self.assertEqual(by_heading["Title > Alpha > Deep"], "deep body")
        self.assertEqual(by_heading["Title > Beta"], "beta body")


if __name__ == "__main__":
    unittest.main()
