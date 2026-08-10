"""pgvector database connection and session management."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from energy_rag.config import settings

logger = logging.getLogger(__name__)


class PgVectorDatabase:
    """Manages async SQLAlchemy engine and sessions for pgvector."""

    def __init__(self, database_url: str | None = None):
        self.database_url = database_url or settings.database_url
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    @property
    def engine(self) -> AsyncEngine:
        """Get or create async engine."""
        if self._engine is None:
            self._engine = create_async_engine(
                self.database_url,
                echo=False,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
            )
            logger.info("Created database engine")
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Get or create session factory."""
        if self._session_factory is None:
            self._session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,
            )
        return self._session_factory

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get a database session."""
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def create_tables(self) -> None:
        """Create all tables (use with caution in production)."""
        from energy_rag.storage.models import Base

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Created database tables")

    async def drop_tables(self) -> None:
        """Drop all tables (use with caution)."""
        from energy_rag.storage.models import Base

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        logger.info("Dropped database tables")

    async def health_check(self) -> bool:
        """Check database connectivity."""
        try:
            async with self.session() as session:
                await session.execute("SELECT 1")
            return True
        except Exception as e:
            logger.error("Database health check failed: %s", e)
            return False

    async def close(self) -> None:
        """Close engine connections."""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            logger.info("Closed database connections")


# Global database instance
_db: PgVectorDatabase | None = None


def get_database() -> PgVectorDatabase:
    """Get global database instance."""
    global _db
    if _db is None:
        _db = PgVectorDatabase()
    return _db


async def init_database(database_url: str | None = None) -> PgVectorDatabase:
    """Initialize global database instance."""
    global _db
    _db = PgVectorDatabase(database_url)
    return _db
