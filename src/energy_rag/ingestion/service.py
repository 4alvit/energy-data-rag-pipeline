"""Ingestion service shared by the REST API and the CLI.

Chunks are embedded and stored via the LangChain pgvector vector store so
that /query can actually retrieve them. Ingestion runs are tracked in the
``ingestion_runs`` audit table.
"""

import logging
from pathlib import Path

from langchain_core.documents import Document
from sqlalchemy import text

from energy_rag.chunking import create_chunker
from energy_rag.ingestion import create_ingestion_pipeline
from energy_rag.retrieval.factory import get_vector_store
from energy_rag.storage.pgvector import ensure_vector_extension, get_database, init_database
from energy_rag.storage.repository import DocumentRepository

logger = logging.getLogger(__name__)

# The PGVector table is created by langchain_postgres itself (fixed default
# name; the collection only lives in a separate table).
_EMBEDDING_TABLE = "langchain_pg_embedding"

# PGVector inserts one VALUES row per chunk with ~5 bind params each; asyncpg
# rejects statements above 32767 args (~6553 rows), so store texts in batches.
# If a crash lands between batches, the source-level idempotency check will
# skip the whole file on retry — re-ingest requires wiping those partial rows.
_INSERT_BATCH_SIZE = 5000


async def _stored_sources(session) -> set[str]:
    """Source paths already present in the vector store (for idempotent re-ingest)."""
    rows = await session.execute(
        text(
            f"select distinct cmetadata->>'source' from {_EMBEDDING_TABLE} where cmetadata ? 'source'"
        )
    )
    return {r[0] for r in rows if r[0]}


def _fresh_documents(documents: list[Document], stored_sources: set[str]) -> list[Document]:
    """Drop documents whose source file was already ingested."""
    return [d for d in documents if d.metadata.get("source") not in stored_sources]


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
            stored_sources = await _stored_sources(session)
            for path in paths:
                if not path.exists():
                    logger.warning("Path does not exist, skipping: %s", path)
                    continue

                documents = _load_documents(pipeline, source_type, path, recursive)
                fresh = _fresh_documents(documents, stored_sources)
                skipped = len(documents) - len(fresh)
                if skipped:
                    logger.info("Skipping %d already-ingested documents for %s", skipped, path)
                if not fresh:
                    continue

                # Embed and store via the vector store (async-native path),
                # in batches to stay under the asyncpg statement arg limit.
                path_chunks = 0
                for i in range(0, len(fresh), _INSERT_BATCH_SIZE):
                    batch = fresh[i : i + _INSERT_BATCH_SIZE]
                    ids = await vector_store.aadd_texts(
                        texts=[d.page_content for d in batch],
                        metadatas=[d.metadata for d in batch],
                    )
                    stored_sources.update(d.metadata.get("source") for d in batch)
                    path_chunks += len(ids)

                docs_processed += 1
                chunks_created += path_chunks
                logger.info("Stored %d chunks from %s", path_chunks, path)

            await repo.complete_ingestion_run(
                run_id=run.id,
                status="completed",
                documents_processed=docs_processed,
                chunks_created=chunks_created,
            )
        except Exception as exc:
            logger.exception("Ingestion failed")
            # The failing statement poisons the session's transaction; roll
            # back so recording the failed run gets a clean transaction.
            await session.rollback()
            await repo.complete_ingestion_run(
                run_id=run.id,
                status="failed",
                error_message=str(exc),
            )
            raise

    return docs_processed, chunks_created
