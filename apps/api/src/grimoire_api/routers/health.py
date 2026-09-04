"""Health check router."""

import asyncio
import logging
from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..config import settings
from ..dependencies import get_db_connection
from ..models.response import COMMON_ERROR_RESPONSES
from ..services.vectorizer import validate_weaviate_schema
from ..utils.exceptions import ServiceUnavailableError, VectorizerError

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


router = APIRouter(prefix="/api/v1", tags=["health"], responses=COMMON_ERROR_RESPONSES)


async def _readiness_check(request: Request) -> HealthResponse:
    """DB と Weaviate の readiness を確認する."""
    try:
        database_ready = await get_db_connection().fetch_one("SELECT 1") is not None
    except Exception:
        logger.exception("Database readiness check failed")
        database_ready = False

    manager = getattr(request.app.state, "weaviate_manager", None)
    weaviate_client = await manager.get_ready_client() if manager is not None else None
    weaviate_ready = weaviate_client is not None
    schema_error: str | None = None
    schema_reason: str | None = None
    if weaviate_client is not None:
        try:
            await asyncio.to_thread(validate_weaviate_schema, weaviate_client)
        except VectorizerError as exc:
            schema_error = str(exc)
            schema_reason = "schema_incompatible"
            weaviate_ready = False
            logger.error("Weaviate schema readiness check failed: %s", exc)
        except Exception:
            schema_error = "Weaviate schema could not be inspected"
            schema_reason = "schema_check_failed"
            weaviate_ready = False
            logger.exception("Weaviate schema readiness check failed")
    unavailable = []
    if not database_ready:
        unavailable.append("database")
    if not weaviate_ready:
        unavailable.append("Weaviate")
    ready = database_ready and weaviate_ready
    if not ready:
        details = None
        if schema_error is not None and schema_reason is not None:
            details = [
                {
                    "dependency": "weaviate",
                    "reason": schema_reason,
                    "message": schema_error,
                }
            ]
        raise ServiceUnavailableError(
            f"Unavailable dependencies: {', '.join(unavailable)}",
            details=details,
        )

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


@router.get("/health/ready", response_model=HealthResponse)
async def readiness_check(request: Request) -> HealthResponse:
    """依存サービスを含めてリクエスト受付可能か確認する."""
    return await _readiness_check(request)


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    """後方互換のため readiness と同じ結果を返す."""
    return await _readiness_check(request)
