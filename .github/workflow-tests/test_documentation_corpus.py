"""Run the same corpus tests before the expensive application CI is selected."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_tests(loader, tests, pattern):
    spec = importlib.util.spec_from_file_location(
        "workflow_docs_corpus", ROOT / "tests/unit/test_docs_corpus.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return loader.loadTestsFromModule(module)
