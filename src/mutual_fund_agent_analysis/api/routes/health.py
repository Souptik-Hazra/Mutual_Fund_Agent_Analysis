"""Liveness and readiness endpoints."""
from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from mutual_fund_agent_analysis.database.session import check_database_connection

router = APIRouter(tags=["health"])


@router.get("/health/live", summary="Liveness probe")
def liveness() -> dict[str, str]:
    """Confirm that the API process is running."""
    return {"status": "ok"}


@router.get("/health/ready", summary="Readiness probe")
def readiness() -> dict[str, str]:
    """Confirm that required infrastructure is reachable."""
    try:
        check_database_connection()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc
    return {"status": "ready", "database": "connected"}
