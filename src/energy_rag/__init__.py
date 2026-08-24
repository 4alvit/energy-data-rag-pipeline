"""Energy RAG Pipeline - Main package."""

from importlib import metadata

try:
    __version__ = metadata.version("energy-rag-pipeline")
except metadata.PackageNotFoundError:  # pragma: no cover - not installed
    __version__ = "0.0.0.dev0"

__all__ = ["__version__"]
