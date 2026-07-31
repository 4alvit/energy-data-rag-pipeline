"""CLI script to ingest Victron PDF manuals."""

import argparse
import logging
import sys
from pathlib import Path

from energy_rag.chunking import create_chunker
from energy_rag.ingestion import create_ingestion_pipeline
from energy_rag.storage.pgvector import init_database, get_database
from energy_rag.storage.repository import DocumentRepository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def ingest_manuals(
    source_dir: Path,
    chunk_strategy: str = "technical",
    recursive: bool = True,
) -> tuple[int, int]:
    """Ingest PDF manuals from directory."""
    # Initialize database
    await init_database()

    db = get_database()
    chunker = create_chunker(chunk_strategy)
    pipeline = create_ingestion_pipeline(chunker)

    docs_processed = 0
    chunks_created = 0

    async with db.session() as session:
        repo = DocumentRepository(session)

        # Create ingestion run
        run = await repo.create_ingestion_run(
            source_type="pdf",
            source_path=str(source_dir),
        )

        try:
            documents = list(pipeline.ingest_pdf_directory(source_dir, recursive))

            if documents:
                doc_models = [
                    repo.model_class(
                        content=doc.page_content,
                        metadata=doc.metadata,
                    )
                    for doc in documents
                ]
                await repo.add_batch(doc_models)
                docs_processed = 1  # Count as one directory
                chunks_created = len(documents)

            await repo.complete_ingestion_run(
                run_id=run.id,
                status="completed",
                documents_processed=docs_processed,
                chunks_created=chunks_created,
            )

        except Exception as e:
            logger.exception("Ingestion failed: %s", e)
            await repo.complete_ingestion_run(
                run_id=run.id,
                status="failed",
                error_message=str(e),
            )
            raise

    return docs_processed, chunks_created


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Ingest Victron PDF manuals")
    parser.add_argument(
        "--source-dir",
        type=Path,
        required=True,
        help="Directory containing PDF manuals",
    )
    parser.add_argument(
        "--chunk-strategy",
        default="technical",
        choices=["technical", "markdown", "recursive", "fixed"],
        help="Chunking strategy",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Do not search subdirectories",
    )

    args = parser.parse_args()

    if not args.source_dir.exists():
        logger.error("Source directory does not exist: %s", args.source_dir)
        sys.exit(1)

    logger.info("Starting ingestion from %s", args.source_dir)

    try:
        docs, chunks = await ingest_manuals(
            source_dir=args.source_dir,
            chunk_strategy=args.chunk_strategy,
            recursive=not args.no_recursive,
        )
        logger.info("Ingestion complete: %d documents, %d chunks", docs, chunks)
    except Exception as e:
        logger.error("Ingestion failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())