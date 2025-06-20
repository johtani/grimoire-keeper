"""Response models."""

from datetime import datetime

from pydantic import BaseModel


class ProcessUrlResponse(BaseModel):
    """URL処理レスポンス."""

    status: str
    page_id: int
    message: str


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
