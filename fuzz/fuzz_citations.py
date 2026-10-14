import sys
import types
from pathlib import Path

import atheris

ROOT = Path(__file__).resolve().parents[1]
package = types.ModuleType("energy_rag")
package.__path__ = [str(ROOT / "src/energy_rag")]
sys.modules[package.__name__] = package
package = types.ModuleType("energy_rag.retrieval")
package.__path__ = [str(ROOT / "src/energy_rag/retrieval")]
sys.modules[package.__name__] = package

with atheris.instrument_imports():
    from energy_rag.retrieval.citations import extract_citations, format_citations


def test_one_input(data: bytes) -> None:
    from langchain_core.documents import Document

    answer = data.decode("utf-8", errors="replace")
    corpus = {"doc_1": Document(page_content="Synthetic source", metadata={"title": "Fixture"})}
    cleaned, sources = extract_citations(answer, corpus)
    assert cleaned == answer  # nosec B101 - intentional test oracle
    assert all(source["index"] == 1 for source in sources)  # nosec B101 - intentional test oracle
    assert len(sources) <= 1  # nosec B101 - intentional test oracle
    assert format_citations(answer, sources).startswith(answer)  # nosec B101 - intentional test oracle


if __name__ == "__main__":
    atheris.Setup(sys.argv, atheris.instrument_func(test_one_input))
    atheris.Fuzz()
