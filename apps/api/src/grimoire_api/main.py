"""FastAPI application main module."""

import logging
import os
import re
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from grimoire_shared.telemetry import redact_http_url, setup_telemetry
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlite3 import SQLite3Instrumentor
from starlette.exceptions import HTTPException

from .config import settings
from .routers import health, pages, process, retry, search, system_info
from .services.weaviate_connection import WeaviateConnectionManager
from .utils.database_init import ensure_database_initialized
from .utils.exceptions import GrimoireAPIError

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,128}$")
HTTP_ERROR_CODES = {
    400: ("bad_request", "The request could not be processed"),
    401: ("unauthorized", "Authentication is required"),
    403: ("forbidden", "The request is not permitted"),
    404: ("not_found", "The requested resource was not found"),
    405: ("method_not_allowed", "The HTTP method is not allowed"),
    409: ("conflict", "The request conflicts with the current resource state"),
    422: ("validation_error", "Request validation failed"),
    503: ("service_unavailable", "The service is temporarily unavailable"),
}

# 環境変数の必須チェック（テスト環境以外）
if not os.getenv("PYTEST_CURRENT_TEST"):
    settings.validate_api_required_vars()

# OpenTelemetryの初期化
telemetry_is_enabled = setup_telemetry("grimoire-api")

# 自動計装の設定
if telemetry_is_enabled:
    HTTPXClientInstrumentor().instrument(request_hook=redact_http_url)
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
        query_timeout=settings.WEAVIATE_QUERY_TIMEOUT,
        insert_timeout=settings.WEAVIATE_INSERT_TIMEOUT,
        monitor_interval=settings.WEAVIATE_MONITOR_INTERVAL,
        retry_backoff_base=settings.WEAVIATE_RETRY_BACKOFF_BASE,
        retry_backoff_max=settings.WEAVIATE_RETRY_BACKOFF_MAX,
        retry_jitter=settings.WEAVIATE_RETRY_JITTER,
        retry_after_max=settings.WEAVIATE_RETRY_AFTER_MAX,
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


def _request_id(request: Request) -> str:
    """Return the sanitized request ID assigned to a request."""
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str):
        return request_id
    request_id = uuid.uuid4().hex
    request.state.request_id = request_id
    return request_id


@app.middleware("http")
async def attach_request_id(request: Request, call_next: Any) -> Any:
    """Propagate a safe request ID and expose it on every response."""
    supplied_id = request.headers.get(REQUEST_ID_HEADER, "")
    request.state.request_id = (
        supplied_id if REQUEST_ID_PATTERN.fullmatch(supplied_id) else uuid.uuid4().hex
    )
    try:
        response = await call_next(request)
    except Exception as exc:
        response = await unhandled_exception_handler(request, exc)
    response.headers[REQUEST_ID_HEADER] = request.state.request_id
    return response


def _error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    request_id = _request_id(request)
    content: dict[str, Any] = {
        "error": {"code": code, "message": message, "request_id": request_id}
    }
    if details is not None:
        content["error"]["details"] = details
    return JSONResponse(
        status_code=status_code,
        content=content,
        headers={REQUEST_ID_HEADER: request_id},
    )


@app.exception_handler(GrimoireAPIError)
async def domain_exception_handler(
    request: Request, exc: GrimoireAPIError
) -> JSONResponse:
    """Convert domain errors without exposing their internal messages."""
    if exc.status_code >= 500:
        logger.exception(
            "Domain error request_id=%s code=%s",
            _request_id(request),
            exc.code,
            exc_info=exc,
        )
    return _error_response(
        request,
        exc.status_code,
        exc.code,
        exc.public_message,
        details=exc.details,
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Normalize framework HTTP errors to the public contract."""
    code, message = HTTP_ERROR_CODES.get(
        exc.status_code, ("http_error", "The request failed")
    )
    return _error_response(request, exc.status_code, code, message)


@app.exception_handler(RequestValidationError)
async def request_validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Use the common validation contract for every API endpoint."""
    details = [
        {
            "location": [str(part) for part in error["loc"]],
            "message": (
                "Field required"
                if error["type"] == "missing"
                else "Unexpected field"
                if error["type"] == "extra_forbidden"
                else "Invalid value"
            ),
            "type": error["type"],
        }
        for error in exc.errors()
    ]
    return _error_response(
        request,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "validation_error",
        "Request validation failed",
        details,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log unexpected failures and return a non-sensitive response."""
    logger.exception(
        "Unhandled API error request_id=%s",
        _request_id(request),
        exc_info=exc,
    )
    return _error_response(
        request,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "internal_error",
        "An internal error occurred",
    )


# FastAPI自動計装
if telemetry_is_enabled:
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
