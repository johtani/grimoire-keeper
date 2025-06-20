"""Database models."""

from dataclasses import dataclass
from datetime import datetime


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


@dataclass
class ProcessLog:
    """処理ログデータモデル."""

    id: int | None
    page_id: int | None
    url: str
    status: str
    error_message: str | None
    created_at: datetime
