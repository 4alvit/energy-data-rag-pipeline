"""Ingestion pipeline orchestration."""

import logging
from collections.abc import Iterator
from pathlib import Path

from langchain_core.documents import Document

from energy_rag.ingestion.forum_loader import (
    load_forum_html,
    load_forum_json,
    load_victron_community_export,
)
from energy_rag.ingestion.pdf_loader import load_victron_manual

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """Orchestrate document ingestion from multiple sources."""

    def __init__(self, chunker=None):
        self.chunker = chunker

    def ingest_pdf_directory(self, directory: Path, recursive: bool = True) -> Iterator[Document]:
        """Ingest all PDF files from a directory."""
        pattern = "**/*.pdf" if recursive else "*.pdf"
        pdf_files = list(directory.glob(pattern))

        logger.info("Found %d PDF files in %s", len(pdf_files), directory)

        for pdf_file in pdf_files:
            try:
                logger.info("Processing %s", pdf_file)
                documents = load_victron_manual(pdf_file)

                if self.chunker:
                    documents = self.chunker.chunk_documents(documents)

                for doc in documents:
                    yield doc

            except Exception as e:
                logger.error("Failed to process %s: %s", pdf_file, e)
                continue

    def ingest_forum_html_directory(self, directory: Path, recursive: bool = True) -> Iterator[Document]:
        """Ingest all HTML forum files from a directory."""
        pattern = "**/*.html" if recursive else "*.html"
        html_files = list(directory.glob(pattern))

        logger.info("Found %d HTML files in %s", len(html_files), directory)

        for html_file in html_files:
            try:
                logger.info("Processing %s", html_file)
                documents = load_forum_html(html_file)

                if self.chunker:
                    documents = self.chunker.chunk_documents(documents)

                for doc in documents:
                    yield doc

            except Exception as e:
                logger.error("Failed to process %s: %s", html_file, e)
                continue

    def ingest_forum_json_directory(self, directory: Path, recursive: bool = True) -> Iterator[Document]:
        """Ingest all JSON forum files from a directory."""
        pattern = "**/*.json" if recursive else "*.json"
        json_files = list(directory.glob(pattern))

        logger.info("Found %d JSON files in %s", len(json_files), directory)

        for json_file in json_files:
            try:
                logger.info("Processing %s", json_file)
                documents = load_forum_json(json_file)

                if self.chunker:
                    documents = self.chunker.chunk_documents(documents)

                for doc in documents:
                    yield doc

            except Exception as e:
                logger.error("Failed to process %s: %s", json_file, e)
                continue

    def ingest_victron_community_export(self, export_dir: Path) -> Iterator[Document]:
        """Ingest Victron community Discourse export."""
        logger.info("Processing Victron community export from %s", export_dir)

        try:
            documents = load_victron_community_export(export_dir)

            if self.chunker:
                documents = self.chunker.chunk_documents(documents)

            for doc in documents:
                yield doc

        except Exception as e:
            logger.error("Failed to process community export: %s", e)

    def ingest_mixed_directory(self, directory: Path, recursive: bool = True) -> Iterator[Document]:
        """Ingest all supported file types from a directory."""
        # PDFs
        yield from self.ingest_pdf_directory(directory, recursive)

        # HTML
        yield from self.ingest_forum_html_directory(directory, recursive)

        # JSON
        yield from self.ingest_forum_json_directory(directory, recursive)


def create_ingestion_pipeline(chunker=None) -> IngestionPipeline:
    """Factory function to create ingestion pipeline."""
    return IngestionPipeline(chunker=chunker)