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


class PageResponse(BaseModel):
    """ページ詳細レスポンス."""

    id: int
    url: str
    title: str
    memo: str | None
    summary: str
    keywords: list[str]
    created_at: datetime
    updated_at: datetime | None
    weaviate_id: str | None


class PageListItem(BaseModel):
    """ページ一覧アイテム."""

    id: int
    url: str
    title: str
    memo: str | None
    summary: str
    keywords: list[str]
    created_at: datetime


class PageListResponse(BaseModel):
    """ページ一覧レスポンス."""

    pages: list[PageListItem]
    total: int
    limit: int
    offset: int
