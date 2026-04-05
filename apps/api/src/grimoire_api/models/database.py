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


@dataclass
class ProcessLog:
    """処理ログデータモデル."""

    id: int | None
    page_id: int | None
    url: str
    status: str
    error_message: str | None
    created_at: datetime
