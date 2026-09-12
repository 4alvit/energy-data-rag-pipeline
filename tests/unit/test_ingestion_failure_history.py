"""Audit persistence across real SQLAlchemy rollbacks, without external services."""

from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.documents import Document
from sqlalchemy import select, text

from energy_rag.ingestion import service
from energy_rag.storage.models import IngestionRunModel
from energy_rag.storage.pgvector import PgVectorDatabase


@pytest.fixture
async def audit_database(tmp_path, monkeypatch):
    """Use an isolated SQLite database with the production session lifecycle."""
    database = PgVectorDatabase(database_url=f"sqlite+aiosqlite:///{tmp_path / 'audit.sqlite'}")
    engine = database.engine
    async with engine.begin() as connection:
        await connection.run_sync(IngestionRunModel.__table__.create)
        await connection.execute(text("CREATE TABLE processing_marker (value INTEGER)"))

    monkeypatch.setattr(service, "init_database", AsyncMock())
    monkeypatch.setattr(service, "ensure_vector_extension", AsyncMock())
    monkeypatch.setattr(service, "get_database", lambda: database)
    monkeypatch.setattr(service, "create_chunker", Mock())
    monkeypatch.setattr(service, "create_ingestion_pipeline", Mock())

    async def stored_sources(session):
        # This write must disappear when ingestion raises and rolls back.
        await session.execute(text("INSERT INTO processing_marker VALUES (1)"))
        return set()

    monkeypatch.setattr(service, "_stored_sources", stored_sources)
    yield database
    await engine.dispose()


@pytest.mark.parametrize("failure_stage", ["load", "embed", "initialize"])
async def test_failure_audit_survives_processing_rollback(
    audit_database, monkeypatch, tmp_path, failure_stage
):
    """Failed work rolls back, but its audit row and original error survive."""
    source = tmp_path / "manual.pdf"
    source.touch()
    original_error = RuntimeError(f"{failure_stage} failed")
    documents = [Document(page_content="Manual", metadata={"source": str(source)})]
    loader = Mock(return_value=documents)
    store = Mock(aadd_texts=AsyncMock(return_value=["chunk-1"]))
    factory = Mock(return_value=store)
    if failure_stage == "load":
        loader.side_effect = original_error
    elif failure_stage == "embed":
        store.aadd_texts.side_effect = original_error
    else:
        factory.side_effect = original_error
    monkeypatch.setattr(service, "_load_documents", loader)
    monkeypatch.setattr(service, "get_vector_store", factory)

    with pytest.raises(RuntimeError) as raised:
        await service.run_ingestion("pdf", [source])
    assert raised.value is original_error

    # Reopen a session: checking the in-memory ORM object would miss rollback bugs.
    async with audit_database.session() as session:
        runs = (await session.scalars(select(IngestionRunModel))).all()
        assert len(runs) == 1
        run = runs[0]
        assert run.status == "failed"
        assert run.source_path == str(source)
        assert run.error_message == str(original_error)
        assert run.completed_at is not None
        assert run.documents_processed == 0
        assert run.chunks_created == 0
        assert (await session.scalar(text("SELECT count(*) FROM processing_marker"))) == 0


async def test_audit_write_failure_does_not_replace_original_error(
    audit_database, monkeypatch, tmp_path
):
    """A secondary audit outage must not hide the ingestion failure."""
    source = tmp_path / "manual.pdf"
    source.touch()
    original_error = ValueError("document loading failed")
    monkeypatch.setattr(service, "get_vector_store", Mock())
    monkeypatch.setattr(service, "_load_documents", Mock(side_effect=original_error))
    monkeypatch.setattr(
        service.DocumentRepository,
        "complete_ingestion_run",
        AsyncMock(side_effect=RuntimeError("audit update unavailable")),
    )
    with pytest.raises(ValueError) as raised:
        await service.run_ingestion("pdf", [source])
    assert raised.value is original_error


async def test_successful_run_is_completed(audit_database, monkeypatch, tmp_path):
    """Successful processing still commits its counts and completion time."""
    source = tmp_path / "manual.pdf"
    source.touch()
    monkeypatch.setattr(
        service,
        "_load_documents",
        Mock(return_value=[Document(page_content="Manual", metadata={"source": str(source)})]),
    )
    monkeypatch.setattr(
        service,
        "get_vector_store",
        Mock(return_value=Mock(aadd_texts=AsyncMock(return_value=["1"]))),
    )
    assert await service.run_ingestion("pdf", [source]) == (1, 1)
    async with audit_database.session() as session:
        run = (await session.scalars(select(IngestionRunModel))).one()
        assert run.status == "completed"
        assert run.documents_processed == 1
        assert run.chunks_created == 1
        assert run.completed_at is not None
