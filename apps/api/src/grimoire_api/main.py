"""FastAPI application main module."""

import asyncio
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
    success = await ensure_database_initialized()
    if success:
        logger.info("Database initialized successfully")
    else:
        logger.warning("Database initialization failed, but continuing startup")

    job_worker: JobWorker | None = None
    retiring_worker: JobWorker | None = None
    pending_worker_start: asyncio.Task[None] | None = None

    async def start_job_worker_now(weaviate_client: Any) -> None:
        """Build and start a worker for the supplied client."""
        nonlocal job_worker
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
                weaviate_client,
            ),
            page_repo=page_repo,
            log_repo=log_repo,
            file_repo=file_repo,
            job_repo=job_repo,
        )
        new_job_worker = JobWorker(job_repo, page_repo, log_repo, processor)
        await new_job_worker.start()
        job_worker = new_job_worker
        app.state.job_worker = new_job_worker
        logger.info("Persistent job worker started")

    async def start_job_worker(weaviate_client: Any) -> None:
        """Start now, or defer until the retiring worker has fully stopped."""
        nonlocal pending_worker_start, retiring_worker
        if job_worker is not None or pending_worker_start is not None:
            return
        if retiring_worker is None:
            await start_job_worker_now(weaviate_client)
            return

        worker_to_wait = retiring_worker

        async def start_after_retirement() -> None:
            nonlocal pending_worker_start, retiring_worker
            try:
                await asyncio.shield(worker_to_wait.wait_stopped())
                if retiring_worker is worker_to_wait:
                    retiring_worker = None
                manager = app.state.weaviate_manager
                while manager.get_client() is weaviate_client and job_worker is None:
                    try:
                        await start_job_worker_now(weaviate_client)
                    except Exception:
                        logger.exception(
                            "Persistent job worker restart failed; retrying"
                        )
                        await asyncio.sleep(settings.WEAVIATE_MONITOR_INTERVAL)
            finally:
                pending_worker_start = None

        pending_worker_start = asyncio.create_task(
            start_after_retirement(), name="grimoire-job-worker-restart"
        )
        logger.info("Persistent job worker restart deferred until old worker stops")

    async def stop_job_worker() -> None:
        """Stop the worker before discarding its Weaviate client."""
        nonlocal job_worker, pending_worker_start, retiring_worker
        pending_start = pending_worker_start
        if pending_start is not None:
            pending_worker_start = None
            pending_start.cancel()
            await asyncio.gather(pending_start, return_exceptions=True)
        worker = job_worker
        if worker is None:
            return
        job_worker = None
        app.state.job_worker = None
        try:
            stopped = await worker.stop(timeout=settings.WEAVIATE_WORKER_STOP_TIMEOUT)
            if stopped:
                logger.info("Persistent job worker stopped")
            else:
                retiring_worker = worker
                logger.warning("Persistent job worker is still retiring")
        except Exception:
            logger.exception("Persistent job worker stop failed")

    weaviate_manager = WeaviateConnectionManager(
        host=settings.WEAVIATE_HOST,
        port=settings.WEAVIATE_PORT,
        api_key=settings.OPENAI_API_KEY,
        startup_attempts=settings.WEAVIATE_STARTUP_RETRY_ATTEMPTS,
        startup_interval=settings.WEAVIATE_STARTUP_RETRY_INTERVAL,
        startup_timeout=settings.WEAVIATE_STARTUP_TIMEOUT,
        connect_timeout=settings.WEAVIATE_CONNECT_TIMEOUT,
        monitor_interval=settings.WEAVIATE_MONITOR_INTERVAL,
        on_connected=start_job_worker,
        on_disconnected=stop_job_worker,
    )
    app.state.weaviate_manager = weaviate_manager
    app.state.job_worker = None
    await weaviate_manager.start()

    yield

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
