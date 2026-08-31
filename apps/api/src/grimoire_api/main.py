"""FastAPI application main module."""

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from grimoire_shared.telemetry import setup_telemetry
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlite3 import SQLite3Instrumentor

from .config import settings
from .routers import health, pages, process, retry, search, system_info
from .services.weaviate_connection import WeaviateConnectionManager
from .utils.database_init import ensure_database_initialized
from .utils.exceptions import ResourceConflictError, ResourceNotFoundError

logger = logging.getLogger(__name__)

PAGE_RESOURCE_ROUTES = frozenset(
    {
        "/api/v1/process-status/{page_id}",
        "/api/v1/pages/{page_id}",
        "/api/v1/pages/{page_id}/json",
        "/api/v1/pages/{page_id}/repair",
        "/api/v1/pages/{page_id}/url",
        "/api/v1/retry/{page_id}",
        "/api/v1/reprocess/{page_id}",
    }
)

# 環境変数の必須チェック（テスト環境以外）
if not os.getenv("PYTEST_CURRENT_TEST"):
    settings.validate_api_required_vars()

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
        logger.info("Application shutting down")


app = FastAPI(
    title="Grimoire Keeper API",
    description="URL content summarization and search system",
    version="0.1.0",
    lifespan=lifespan,
)


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    content: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details is not None:
        content["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=content)


@app.exception_handler(ResourceNotFoundError)
async def resource_not_found_handler(
    request: Request, exc: ResourceNotFoundError
) -> JSONResponse:
    """Convert domain not-found errors to the common API contract."""
    return _error_response(status.HTTP_404_NOT_FOUND, exc.code, str(exc))


@app.exception_handler(ResourceConflictError)
async def resource_conflict_handler(
    request: Request, exc: ResourceConflictError
) -> JSONResponse:
    """Convert domain conflicts to the common API contract."""
    return _error_response(status.HTTP_409_CONFLICT, exc.code, str(exc))


@app.exception_handler(RequestValidationError)
async def request_validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Use the common validation contract for page-resource APIs."""
    route = request.scope.get("route")
    if getattr(route, "path", None) not in PAGE_RESOURCE_ROUTES:
        return await request_validation_exception_handler(request, exc)

    details = [
        {
            "location": [str(part) for part in error["loc"]],
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors()
    ]
    return _error_response(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "validation_error",
        "Request validation failed",
        details,
    )


# FastAPI自動計装
FastAPIInstrumentor.instrument_app(app)

# ルーター登録
app.include_router(health.router)
app.include_router(process.router)
app.include_router(search.router)
app.include_router(pages.router)
app.include_router(retry.router)
app.include_router(system_info.router)


@app.get("/")
async def root() -> dict[str, str]:
    """ルートエンドポイント."""
    return {"message": "Grimoire Keeper API is running"}
