"""Database models."""

# Pydantic警告を抑制
import warnings
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

warnings.filterwarnings("ignore", category=DeprecationWarning, module="pydantic.*")


class ProcessingStep(str, Enum):
    """処理ステップ名の Enum."""

    DOWNLOADED = "downloaded"
    LLM_PROCESSED = "llm_processed"
    VECTORIZED = "vectorized"
    COMPLETED = "completed"


class PipelineStartStep(str, Enum):
    """パイプラインの開始ステップ."""

    DOWNLOAD = "download"
    LLM = "llm"
    VECTORIZE = "vectorize"


class ReprocessStartStep(str, Enum):
    """API で指定できる再処理開始ステップ."""

    AUTO = "auto"
    DOWNLOAD = "download"
    LLM = "llm"
    VECTORIZE = "vectorize"


class PageStatus(str, Enum):
    """ページの現在状態."""

    QUEUED = "queued"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class JobKind(str, Enum):
    """ジョブ種別."""

    INITIAL = "initial"
    RETRY = "retry"
    REPROCESS = "reprocess"


class JobStatus(str, Enum):
    """ジョブ状態."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class Page:
    """ページデータモデル."""

    id: int | None
    url: str
    title: str
    memo: str | None
    summary: str | None
    keywords: list[str]
    created_at: datetime
    updated_at: datetime
    weaviate_id: str | None
    last_success_step: ProcessingStep | None = None
    status: PageStatus = PageStatus.QUEUED


@dataclass
class Job:
    """永続処理ジョブ."""

    id: int
    page_id: int
    kind: JobKind
    status: JobStatus
    current_step: ProcessingStep | None
    start_step: PipelineStartStep
    attempt: int
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


@dataclass
class ProcessLog:
    """処理ログデータモデル."""

    id: int | None
    page_id: int | None
    url: str
    status: str
    error_message: str | None
    created_at: datetime
