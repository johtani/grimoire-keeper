"""FastAPI application main module."""

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

import weaviate
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from grimoire_shared.telemetry import setup_telemetry
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlite3 import SQLite3Instrumentor

from .config import settings
from .dependencies import (
    get_chunking_service,
    get_db_connection,
    get_file_repository,
    get_jina_client,
)
from .repositories.job_repository import JobRepository
from .repositories.log_repository import LogRepository
from .repositories.page_repository import PageRepository
from .routers import health, pages, process, retry, search
from .services.base_processor import BaseProcessorService
from .services.job_worker import JobWorker
from .services.llm_service import LLMService
from .services.vectorizer import VectorizerService
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
    success = await ensure_database_initialized()
    if success:
        logger.info("Database initialized successfully")
    else:
        logger.warning("Database initialization failed, but continuing startup")

    # 起動時処理 - Weaviate クライアント初期化
    try:
        weaviate_client = weaviate.connect_to_local(
            host=settings.WEAVIATE_HOST,
            port=settings.WEAVIATE_PORT,
            headers={"X-OpenAI-Api-Key": settings.OPENAI_API_KEY},
        )
        app.state.weaviate_client = weaviate_client
        logger.info("Weaviate client initialized successfully")
    except Exception as e:
        app.state.weaviate_client = None
        logger.warning("Weaviate connection failed, continuing startup: %s", e)

    job_worker = None
    if app.state.weaviate_client is not None:
        db = get_db_connection()
        page_repo = PageRepository(db)
        log_repo = LogRepository(db)
        job_repo = JobRepository(db)
        file_repo = get_file_repository()
        processor = BaseProcessorService(
            jina_client=get_jina_client(),
            llm_service=LLMService(file_repo),
            vectorizer=VectorizerService(
                page_repo,
                file_repo,
                get_chunking_service(),
                app.state.weaviate_client,
            ),
            page_repo=page_repo,
            log_repo=log_repo,
            file_repo=file_repo,
            job_repo=job_repo,
        )
        job_worker = JobWorker(job_repo, page_repo, log_repo, processor)
        await job_worker.start()
        app.state.job_worker = job_worker
        logger.info("Persistent job worker started")

    yield

    # 終了時処理
    if job_worker is not None:
        await job_worker.stop()
        logger.info("Persistent job worker stopped")
    if getattr(app.state, "weaviate_client", None) is not None:
        app.state.weaviate_client.close()
        logger.info("Weaviate client closed")
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
