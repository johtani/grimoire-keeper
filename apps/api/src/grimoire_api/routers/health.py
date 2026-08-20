"""Health check router."""

import logging
from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel

from ..config import settings
from ..dependencies import get_db_connection

logger = logging.getLogger(__name__)

try:
    APP_VERSION = version("grimoire-api")
except PackageNotFoundError:
    APP_VERSION = "unknown"


class HealthResponse(BaseModel):
    """ヘルスチェックレスポンス."""

    status: str
    message: str
    version: str
    git_commit: str
    build_date: str
    database: str
    weaviate: str


class LivenessResponse(BaseModel):
    """ライブネスチェックレスポンス."""

    status: str
    message: str
    version: str
    git_commit: str
    build_date: str


router = APIRouter(prefix="/api/v1", tags=["health"])


async def _readiness_check(request: Request, response: Response) -> HealthResponse:
    """DB と Weaviate の readiness を確認する."""
    try:
        database_ready = await get_db_connection().fetch_one("SELECT 1") is not None
    except Exception:
        logger.exception("Database readiness check failed")
        database_ready = False

    manager = getattr(request.app.state, "weaviate_manager", None)
    weaviate_ready = (
        manager is not None and await manager.get_ready_client() is not None
    )
    ready = database_ready and weaviate_ready
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    unavailable = []
    if not database_ready:
        unavailable.append("database")
    if not weaviate_ready:
        unavailable.append("Weaviate")

    return HealthResponse(
        status="healthy" if ready else "unhealthy",
        message=(
            "Grimoire Keeper API is ready"
            if ready
            else f"{', '.join(unavailable)} is not available"
        ),
        version=APP_VERSION,
        git_commit=settings.GIT_COMMIT,
        build_date=settings.BUILD_DATE,
        database="ready" if database_ready else "unavailable",
        weaviate="ready" if weaviate_ready else "unavailable",
    )


@router.get("/health/live", response_model=LivenessResponse)
async def liveness_check() -> LivenessResponse:
    """プロセスが HTTP 要求に応答できることを確認する."""
    return LivenessResponse(
        status="healthy",
        message="Grimoire Keeper API is running",
        version=APP_VERSION,
        git_commit=settings.GIT_COMMIT,
        build_date=settings.BUILD_DATE,
    )


@router.get(
    "/health/ready",
    response_model=HealthResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": HealthResponse,
            "description": "SQLite or Weaviate is unavailable",
        }
    },
)
async def readiness_check(request: Request, response: Response) -> HealthResponse:
    """依存サービスを含めてリクエスト受付可能か確認する."""
    return await _readiness_check(request, response)


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": HealthResponse,
            "description": "SQLite or Weaviate is unavailable",
        }
    },
)
async def health_check(request: Request, response: Response) -> HealthResponse:
    """後方互換のため readiness と同じ結果を返す."""
    return await _readiness_check(request, response)
