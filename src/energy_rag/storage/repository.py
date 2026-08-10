"""Repository for document storage and vector search."""

import logging
import uuid
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from energy_rag.storage.models import DocumentModel, IngestionRunModel
from energy_rag.storage.pgvector import get_database

logger = logging.getLogger(__name__)


class DocumentRepository:
    """Repository for document CRUD and similarity search."""

    def __init__(self, session: AsyncSession | None = None):
        self._session = session
        self._db = get_database()

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("No session provided. Use within a session context.")
        return self._session

    async def add(self, document: DocumentModel) -> DocumentModel:
        """Add a document."""
        self.session.add(document)
        await self.session.flush()
        await self.session.refresh(document)
        return document

    async def add_batch(self, documents: list[DocumentModel]) -> list[DocumentModel]:
        """Add multiple documents efficiently."""
        self.session.add_all(documents)
        await self.session.flush()
        for doc in documents:
            await self.session.refresh(doc)
        return documents

    async def get_by_id(self, doc_id: uuid.UUID) -> DocumentModel | None:
        """Get document by ID."""
        result = await self.session.execute(select(DocumentModel).where(DocumentModel.id == doc_id))
        return result.scalar_one_or_none()

    async def similarity_search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        threshold: float = 0.7,
        filters: dict[str, Any] | None = None,
    ) -> list[tuple[DocumentModel, float]]:
        """
        Perform cosine similarity search with optional metadata filtering.

        Returns list of (document, similarity_score) tuples.
        """
        # Build the query
        stmt = select(
            DocumentModel,
            (1 - DocumentModel.embedding.cosine_distance(query_embedding)).label("similarity"),
        ).where(DocumentModel.embedding.is_not(None))

        # Apply similarity threshold
        stmt = stmt.where(
            (1 - DocumentModel.embedding.cosine_distance(query_embedding)) >= threshold
        )

        # Apply metadata filters
        if filters:
            for key, value in filters.items():
                if isinstance(value, list):
                    stmt = stmt.where(DocumentModel.doc_metadata[key].astext.in_(value))
                elif isinstance(value, dict):
                    # Support for operators: {"$gte": 10}, {"$contains": "term"}
                    for op, val in value.items():
                        if op == "$gte":
                            stmt = stmt.where(
                                DocumentModel.doc_metadata[key].astext.cast(int) >= val
                            )
                        elif op == "$lte":
                            stmt = stmt.where(
                                DocumentModel.doc_metadata[key].astext.cast(int) <= val
                            )
                        elif op == "$contains":
                            stmt = stmt.where(
                                DocumentModel.doc_metadata[key].astext.ilike(f"%{val}%")
                            )
                else:
                    stmt = stmt.where(DocumentModel.doc_metadata[key].astext == str(value))

        # Order by similarity and limit
        stmt = stmt.order_by(text("similarity DESC")).limit(top_k)

        result = await self.session.execute(stmt)
        return [(row[0], float(row[1])) for row in result.all()]

    async def search_by_text(
        self,
        query_text: str,
        top_k: int = 5,
        threshold: float = 0.7,
        filters: dict[str, Any] | None = None,
    ) -> list[tuple[DocumentModel, float]]:
        """Search by text (requires embedding generation externally)."""
        # This would need an embedding function - kept for interface compatibility
        raise NotImplementedError("Use similarity_search with pre-computed embeddings")

    async def count(self, filters: dict[str, Any] | None = None) -> int:
        """Count documents matching filters."""
        stmt = select(func.count(DocumentModel.id))
        if filters:
            for key, value in filters.items():
                stmt = stmt.where(DocumentModel.doc_metadata[key].astext == str(value))
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def delete_by_id(self, doc_id: uuid.UUID) -> bool:
        """Delete document by ID."""
        doc = await self.get_by_id(doc_id)
        if doc:
            await self.session.delete(doc)
            return True
        return False

    async def create_ingestion_run(
        self,
        source_type: str,
        source_path: str,
    ) -> IngestionRunModel:
        """Create a new ingestion run record."""
        run = IngestionRunModel(
            source_type=source_type,
            source_path=source_path,
            status="running",
        )
        self.session.add(run)
        await self.session.flush()
        await self.session.refresh(run)
        return run

    async def complete_ingestion_run(
        self,
        run_id: uuid.UUID,
        status: str,
        documents_processed: int = 0,
        chunks_created: int = 0,
        error_message: str | None = None,
    ) -> IngestionRunModel | None:
        """Complete an ingestion run."""
        run = await self.session.get(IngestionRunModel, run_id)
        if run:
            run.status = status
            run.documents_processed = documents_processed
            run.chunks_created = chunks_created
            run.error_message = error_message
            run.completed_at = func.now()
            await self.session.flush()
            await self.session.refresh(run)
        return run


async def get_repository() -> DocumentRepository:
    """Get a repository instance with a new session."""
    db = get_database()
    async with db.session() as session:
        yield DocumentRepository(session)
