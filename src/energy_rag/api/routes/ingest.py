"""Ingest endpoint for document ingestion."""

import logging
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks

from energy_rag.api.schemas import IngestRequest, IngestResponse
from energy_rag.chunking import create_chunker
from energy_rag.ingestion import create_ingestion_pipeline
from energy_rag.storage.models import DocumentModel
from energy_rag.storage.pgvector import get_database
from energy_rag.storage.repository import DocumentRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("", response_model=IngestResponse)
async def ingest_documents(request: IngestRequest, background_tasks: BackgroundTasks) -> IngestResponse:
    """
    Trigger document ingestion.

    Processes files in background and stores in pgvector.
    """
    run_id = str(uuid4())

    # Start background ingestion
    background_tasks.add_task(
        _run_ingestion,
        run_id=run_id,
        source_type=request.source_type,
        paths=request.paths,
        chunk_strategy=request.chunk_strategy,
    )

    return IngestResponse(
        status="started",
        documents_processed=0,
        chunks_created=0,
        run_id=run_id,
    )


async def _run_ingestion(
    run_id: str,
    source_type: str,
    paths: list[str],
    chunk_strategy: str,
) -> None:
    """Background task to run ingestion."""
    db = get_database()
    chunker = create_chunker(chunk_strategy)
    pipeline = create_ingestion_pipeline(chunker)

    async with db.session() as session:
        repo = DocumentRepository(session)

        # Create ingestion run record
        run = await repo.create_ingestion_run(
            source_type=source_type,
            source_path=", ".join(paths),
        )

        try:
            docs_processed = 0
            chunks_created = 0

            for path_str in paths:
                path = Path(path_str)
                if not path.exists():
                    logger.warning("Path does not exist: %s", path)
                    continue

                documents = []

                if source_type == "pdf":
                    if path.is_dir():
                        documents.extend(pipeline.ingest_pdf_directory(path))
                    else:
                        from energy_rag.ingestion.pdf_loader import load_victron_manual
                        documents.extend(load_victron_manual(path))

                elif source_type == "forum_html":
                    if path.is_dir():
                        documents.extend(pipeline.ingest_forum_html_directory(path))
                    else:
                        from energy_rag.ingestion.forum_loader import load_forum_html
                        documents.extend(load_forum_html(path))

                elif source_type == "forum_json":
                    if path.is_dir():
                        documents.extend(pipeline.ingest_forum_json_directory(path))
                    else:
                        from energy_rag.ingestion.forum_loader import load_forum_json
                        documents.extend(load_forum_json(path))

                else:
                    logger.error("Unknown source type: %s", source_type)
                    continue

                # Store documents
                if documents:
                    doc_models = [
                        DocumentModel(
                            content=doc.page_content,
                            doc_metadata=doc.metadata,
                        )
                        for doc in documents
                    ]
                    # Note: embeddings would be added here via LangChain vector store
                    # For now, storing without embeddings
                    await repo.add_batch(doc_models)
                    docs_processed += 1
                    chunks_created += len(documents)

            await repo.complete_ingestion_run(
                run_id=run.id,
                status="completed",
                documents_processed=docs_processed,
                chunks_created=chunks_created,
            )
            logger.info("Ingestion completed: run_id=%s, docs=%d, chunks=%d", run_id, docs_processed, chunks_created)

        except Exception:
            logger.exception("Ingestion failed for run %s", run_id)
            await repo.complete_ingestion_run(
                run_id=run.id,
                status="failed",
                error_message="Ingestion failed",
            )