"""FastAPI application main module."""

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from grimoire_shared.telemetry import setup_telemetry
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlite3 import SQLite3Instrumentor

from .config import settings
from .dependencies import (
    get_jina_client,
)
from .routers import health, pages, process, retry, search
from .services.weaviate_connection import WeaviateConnectionManager
from .utils.database_init import ensure_database_initialized

# 警告フィルタを適用
from .utils.warnings_filter import *  # noqa: F403, F401

logger = logging.getLogger(__name__)

# 環境変数の必須チェック（テスト環境以外）
if not os.getenv("PYTEST_CURRENT_TEST"):
    settings.validate_required_vars()

# OpenTelemetryの初期化
setup_telemetry("grimoire-api")

# 自動計装の設定
HTTPXClientInstrumentor().instrument()
SQLite3Instrumentor().instrument()


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    """アプリケーションライフサイクル管理."""
    # 起動時処理 - データベース初期化
    await ensure_database_initialized()
    logger.info("Database initialized successfully")

    weaviate_manager = WeaviateConnectionManager(
        host=settings.WEAVIATE_HOST,
        port=settings.WEAVIATE_PORT,
        api_key=settings.OPENAI_API_KEY,
        startup_attempts=settings.WEAVIATE_STARTUP_RETRY_ATTEMPTS,
        startup_interval=settings.WEAVIATE_STARTUP_RETRY_INTERVAL,
        startup_timeout=settings.WEAVIATE_STARTUP_TIMEOUT,
        connect_timeout=settings.WEAVIATE_CONNECT_TIMEOUT,
        monitor_interval=settings.WEAVIATE_MONITOR_INTERVAL,
    )
    app.state.weaviate_manager = weaviate_manager
    try:
        await weaviate_manager.start()
        yield
    finally:
        # 終了時処理
        await weaviate_manager.stop()
        await get_jina_client().close()
        logger.info("Jina client closed")
        logger.info("Application shutting down")


app = FastAPI(
    title="Grimoire Keeper API",
    description="URL content summarization and search system",
    version="0.1.0",
    lifespan=lifespan,
)

# FastAPI自動計装
FastAPIInstrumentor.instrument_app(app)

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ルーター登録
app.include_router(health.router)
app.include_router(process.router)
app.include_router(search.router)
app.include_router(pages.router)
app.include_router(retry.router)


@app.get("/")
async def root() -> dict[str, str]:
    """ルートエンドポイント."""
    return {"message": "Grimoire Keeper API is running"}
