"""Health check endpoint."""

from fastapi import APIRouter

from energy_rag.api.schemas import HealthResponse
from energy_rag.storage.pgvector import get_database

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check with database connectivity."""
    db = get_database()
    db_healthy = await db.health_check()

    return HealthResponse(
        status="healthy" if db_healthy else "degraded",
        database="connected" if db_healthy else "disconnected",
    )


@router.get("/ready")
async def readiness_check() -> dict[str, str]:
    """Kubernetes readiness probe."""
    db = get_database()
    db_healthy = await db.health_check()

    if not db_healthy:
        return {"status": "not ready"}

    return {"status": "ready"}


@router.get("/live")
async def liveness_check() -> dict[str, str]:
    """Kubernetes liveness probe."""
    return {"status": "alive"}
