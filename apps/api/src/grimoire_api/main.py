"""FastAPI application main module."""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from .routers import health, process, search, pages
from .utils.database_init import ensure_database_initialized

# 警告フィルタを適用
from .utils.warnings_filter import *  # noqa: F403, F401


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    """アプリケーションライフサイクル管理."""
    # 起動時処理 - データベース初期化
    success = ensure_database_initialized()
    if success:
        print("✅ Database initialized successfully")
    else:
        print("⚠️ Database initialization failed, but continuing startup")

    yield

    # 終了時処理
    print("🔄 Application shutting down")


app = FastAPI(
    title="Grimoire Keeper API",
    description="URL content summarization and search system",
    version="0.1.0",
    lifespan=lifespan,
)

# ルーター登録
app.include_router(health.router)
app.include_router(process.router)
app.include_router(search.router)
app.include_router(pages.router)


@app.get("/")
async def root() -> dict[str, str]:
    """ルートエンドポイント."""
    return {"message": "Grimoire Keeper API is running"}
