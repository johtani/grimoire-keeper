"""Health check router."""

from fastapi import APIRouter
from pydantic import BaseModel


class HealthResponse(BaseModel):
    """ヘルスチェックレスポンス."""

    status: str
    message: str


router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """ヘルスチェックエンドポイント."""
    return HealthResponse(status="healthy", message="Grimoire Keeper API is running")
