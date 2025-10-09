"""Database models."""

# Pydantic警告を抑制
import warnings
from dataclasses import dataclass
from datetime import datetime

warnings.filterwarnings("ignore", category=DeprecationWarning, module="pydantic.*")


@dataclass
class Page:
    """ページデータモデル."""

    id: int | None
    url: str
    title: str
    memo: str | None
    summary: str | None
    keywords: str | None  # JSON string
    created_at: datetime
    updated_at: datetime
    weaviate_id: str | None
    last_success_step: str | None = None

    @property
    def status(self) -> str:
        """処理ステータスを取得."""
        if self.summary and self.weaviate_id:
            return "completed"
        elif self.summary or self.weaviate_id:
            return "processing"
        else:
            return "failed"


@dataclass
class ProcessLog:
    """処理ログデータモデル."""

    id: int | None
    page_id: int | None
    url: str
    status: str
    error_message: str | None
    created_at: datetime
