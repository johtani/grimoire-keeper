"""Health check router."""

from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel

from ..config import settings

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
    weaviate: str


router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request, response: Response) -> HealthResponse:
    """ヘルスチェックエンドポイント."""
    manager = getattr(request.app.state, "weaviate_manager", None)
    ready = manager is not None and await manager.get_ready_client() is not None
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status="healthy" if ready else "unhealthy",
        message=(
            "Grimoire Keeper API is running" if ready else "Weaviate is not available"
        ),
        version=APP_VERSION,
        git_commit=settings.GIT_COMMIT,
        build_date=settings.BUILD_DATE,
        weaviate="ready" if ready else "unavailable",
    )
