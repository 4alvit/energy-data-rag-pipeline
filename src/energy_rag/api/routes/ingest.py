"""Ingest endpoint for document ingestion."""

import logging
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks

from energy_rag.api.schemas import IngestRequest, IngestResponse
from energy_rag.ingestion.service import run_ingestion

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("", response_model=IngestResponse)
async def ingest_documents(
    request: IngestRequest, background_tasks: BackgroundTasks
) -> IngestResponse:
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
        chunk_strategy=request.chunk_strategy or "technical",
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
    """Background task to run ingestion via the shared service."""
    try:
        docs_processed, chunks_created = await run_ingestion(
            source_type=source_type,
            paths=[Path(p) for p in paths],
            chunk_strategy=chunk_strategy,
        )
        logger.info(
            "Ingestion completed: run_id=%s, docs=%d, chunks=%d",
            run_id,
            docs_processed,
            chunks_created,
        )
    except Exception:
        # Service already recorded the failed ingestion run.
        logger.exception("Ingestion failed for run %s", run_id)
