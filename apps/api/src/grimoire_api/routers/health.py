"""Health check router."""

from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter
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


router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """ヘルスチェックエンドポイント."""
    return HealthResponse(
        status="healthy",
        message="Grimoire Keeper API is running",
        version=APP_VERSION,
        git_commit=settings.GIT_COMMIT,
        build_date=settings.BUILD_DATE,
    )
