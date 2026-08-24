"""Ingestion service shared by the REST API and the CLI.

Chunks are embedded and stored via the LangChain pgvector vector store so
that /query can actually retrieve them. Ingestion runs are tracked in the
``ingestion_runs`` audit table.
"""

import logging
from pathlib import Path

from langchain_core.documents import Document

from energy_rag.chunking import create_chunker
from energy_rag.ingestion import create_ingestion_pipeline
from energy_rag.retrieval.factory import get_vector_store
from energy_rag.storage.pgvector import ensure_vector_extension, get_database, init_database
from energy_rag.storage.repository import DocumentRepository

logger = logging.getLogger(__name__)


def _load_documents(pipeline, source_type: str, path: Path, recursive: bool) -> list[Document]:
    """Load documents from path according to source type."""
    if source_type == "pdf":
        if path.is_dir():
            return list(pipeline.ingest_pdf_directory(path, recursive))
        from energy_rag.ingestion.pdf_loader import load_victron_manual

        return list(load_victron_manual(path))

    if source_type == "forum_html":
        if path.is_dir():
            return list(pipeline.ingest_forum_html_directory(path))
        from energy_rag.ingestion.forum_loader import load_forum_html

        return list(load_forum_html(path))

    if source_type == "forum_json":
        if path.is_dir():
            return list(pipeline.ingest_forum_json_directory(path))
        from energy_rag.ingestion.forum_loader import load_forum_json

        return list(load_forum_json(path))

    raise ValueError(f"Unknown source type: {source_type}")


async def run_ingestion(
    source_type: str,
    paths: list[Path],
    chunk_strategy: str = "technical",
    recursive: bool = True,
) -> tuple[int, int]:
    """Chunk, embed and store documents from the given paths.

    Returns:
        Tuple of (documents_processed, chunks_created).
    """
    await init_database()
    await ensure_vector_extension()

    chunker = create_chunker(chunk_strategy)
    pipeline = create_ingestion_pipeline(chunker)
    vector_store = get_vector_store()

    docs_processed = 0
    chunks_created = 0

    db = get_database()
    async with db.session() as session:
        repo = DocumentRepository(session)
        run = await repo.create_ingestion_run(
            source_type=source_type,
            source_path=", ".join(str(p) for p in paths),
        )

        try:
            for path in paths:
                if not path.exists():
                    logger.warning("Path does not exist, skipping: %s", path)
                    continue

                documents = _load_documents(pipeline, source_type, path, recursive)
                if not documents:
                    continue

                # Embed and store via the vector store (async-native path).
                ids = await vector_store.aadd_texts(
                    texts=[d.page_content for d in documents],
                    metadatas=[d.metadata for d in documents],
                )

                docs_processed += 1
                chunks_created += len(ids)
                logger.info("Stored %d chunks from %s", len(ids), path)

            await repo.complete_ingestion_run(
                run_id=run.id,
                status="completed",
                documents_processed=docs_processed,
                chunks_created=chunks_created,
            )
        except Exception as exc:
            logger.exception("Ingestion failed")
            await repo.complete_ingestion_run(
                run_id=run.id,
                status="failed",
                error_message=str(exc),
            )
            raise

    return docs_processed, chunks_created
