"""FastAPI application main module."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .repositories.database import DatabaseConnection
from .routers import health, process, search


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーションライフサイクル管理."""
    # 起動時処理
    db = DatabaseConnection()
    await db.initialize_tables()

    yield

    # 終了時処理（必要に応じて）
    pass


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


@app.get("/")
async def root():
    """ルートエンドポイント."""
    return {"message": "Grimoire Keeper API is running"}
