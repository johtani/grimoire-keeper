"""Response models."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, JsonValue

from .database import (
    JobStatus,
    PipelineStartStep,
    ProcessingStep,
    RepairStatus,
)


class PageResponseStatus(str, Enum):
    """API で返すページ処理状態."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ProcessStatus(str, Enum):
    """処理状態取得 API の結果種別."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    ERROR = "error"


class APIError(BaseModel):
    """Public API error details."""

    code: str
    message: str
    request_id: str
    details: list[dict[str, Any]] | None = None


class ErrorResponse(BaseModel):
    """Common error response envelope."""

    error: APIError


COMMON_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status_code: {"model": ErrorResponse}
    for status_code in (400, 401, 403, 404, 405, 409, 422, 500, 503)
}


class RetryStatus(str, Enum):
    """個別リトライ・再処理 API の結果種別."""

    NOT_FAILED = "not_failed"
    RETRY_STARTED = "retry_started"
    REPROCESS_STARTED = "reprocess_started"


class BatchRetryStatus(str, Enum):
    """一括リトライ API の結果種別."""

    NO_FAILED_PAGES = "no_failed_pages"
    BATCH_RETRY_STARTED = "batch_retry_started"


class ProcessUrlResponse(BaseModel):
    """URL処理レスポンス."""

    status: str
    page_id: int
    job_id: int | None = None
    message: str


class ProcessStatusPage(BaseModel):
    """処理状態に含まれるページ情報."""

    id: int
    url: str
    title: str
    memo: str | None
    summary: str | None
    keywords: list[str]
    created_at: datetime


class ProcessStatusResponse(BaseModel):
    """処理状態取得レスポンス."""

    status: ProcessStatus
    message: str
    page: ProcessStatusPage | None = None


class SearchResult(BaseModel):
    """検索結果."""

    page_id: int
    chunk_id: int
    url: str
    title: str
    memo: str | None
    content: str
    summary: str
    keywords: list[str]
    created_at: datetime
    score: float


class SearchResponse(BaseModel):
    """検索レスポンス."""

    results: list[SearchResult]
    total: int
    query: str


class PageResponse(BaseModel):
    """ページ詳細レスポンス."""

    id: int
    url: str
    title: str | None
    memo: str | None
    summary: str | None
    keywords: list[str] | None
    status: PageResponseStatus
    created_at: datetime
    updated_at: datetime
    weaviate_id: str | None
    error_message: str | None
    last_success_step: ProcessingStep | None
    has_json_file: bool


class PageListItem(BaseModel):
    """ページ一覧アイテム."""

    id: int
    url: str
    title: str | None
    memo: str | None
    summary: str | None
    created_at: datetime
    status: PageResponseStatus
    has_json_file: bool


class PageListResponse(BaseModel):
    """ページ一覧レスポンス."""

    pages: list[PageListItem]
    total: int
    limit: int
    offset: int
    status_filter: str


class RetryResponse(BaseModel):
    """個別リトライ・再処理レスポンス."""

    status: RetryStatus
    page_id: int
    job_id: int | None = None
    restart_from: PipelineStartStep | None = None
    message: str | None = None


class BatchRetryResponse(BaseModel):
    """一括リトライレスポンス."""

    status: BatchRetryStatus
    total_failed_pages: int
    retry_count: int
    job_ids: list[int] | None = None
    message: str


class RepairReason(BaseModel):
    """修復が必要と判定された理由."""

    code: str
    detail: str


class RepairListItem(BaseModel):
    """修復ケース一覧アイテム."""

    page_id: int
    url: str | None
    report_url: str | None
    source: str
    reasons: list[RepairReason]
    repair_status: RepairStatus
    detected_at: datetime
    resolved_at: datetime | None


class RepairListResponse(BaseModel):
    """修復ケース一覧レスポンス."""

    repairs: list[RepairListItem]
    total: int


class RepairScanResponse(BaseModel):
    """修復スキャンレスポンス."""

    scanned: int
    pending: int
    resolved: int


class RepairImportResponse(BaseModel):
    """修復レポート取込レスポンス."""

    imported: int
    missing_pages: int
    url_mismatches: int


class JsonValidationResponse(BaseModel):
    """保存済み JSON の検証結果."""

    valid: bool
    reasons: list[RepairReason]


class LatestJobResponse(BaseModel):
    """修復詳細に含まれる最新ジョブ."""

    id: int
    status: JobStatus
    start_step: PipelineStartStep
    current_step: ProcessingStep | None
    error_message: str | None


class RepairDetailResponse(BaseModel):
    """ページ修復詳細レスポンス."""

    page_id: int
    url: str
    repair_status: RepairStatus | None
    reasons: list[RepairReason]
    json_validation: JsonValidationResponse
    latest_error: str | None
    latest_job: LatestJobResponse | None
    weaviate_registered: bool | None


class UpdatePageUrlResponse(BaseModel):
    """ページ URL 更新レスポンス."""

    current_url: str
    new_url: str
    status: PageResponseStatus


class DeletePageResponse(BaseModel):
    """repair ページ削除レスポンス."""

    page_id: int
    url: str
    status: str


class ExternalServiceInfo(BaseModel):
    """External service used by Grimoire Keeper."""

    name: str
    purpose: str
    model: str | None = None


class VectorizerInfo(BaseModel):
    """Named vector configuration read from Weaviate."""

    name: str
    vectorizer: str
    model: dict[str, JsonValue]
    uses_module_default: bool


class WeaviateCollectionInfo(BaseModel):
    """Vectorizer configuration for a Weaviate collection."""

    name: str
    vectors: list[VectorizerInfo]


class WeaviateSystemInfo(BaseModel):
    """Availability and schema information for Weaviate."""

    status: str
    message: str
    collections: list[WeaviateCollectionInfo]


class SystemInfoResponse(BaseModel):
    """Public, non-secret runtime service information."""

    services: list[ExternalServiceInfo]
    weaviate: WeaviateSystemInfo
