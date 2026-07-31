"""Ingestion package."""

from energy_rag.ingestion.forum_loader import (
    fetch_forum_url,
    load_forum_html,
    load_forum_json,
    load_victron_community_export,
)
from energy_rag.ingestion.pdf_loader import (
    load_pdf_as_markdown,
    load_pdf_pages,
    load_victron_manual,
)
from energy_rag.ingestion.pipeline import IngestionPipeline, create_ingestion_pipeline

__all__ = [
    "IngestionPipeline",
    "create_ingestion_pipeline",
    "fetch_forum_url",
    "load_forum_html",
    "load_forum_json",
    "load_pdf_as_markdown",
    "load_pdf_pages",
    "load_victron_community_export",
    "load_victron_manual",
]