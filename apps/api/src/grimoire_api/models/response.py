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
    
    @property
    def display_title(self) -> str:
        """表示用タイトル（pageIdとchunkId付き）."""
        return f"{self.title} (p{self.page_id}-c{self.chunk_id})"
    
    def model_dump(self, **kwargs) -> dict:
        """モデルを辞書に変換し、display_titleを含める."""
        data = super().model_dump(**kwargs)
        data["display_title"] = self.display_title
        return data


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
    keywords: str | None
    status: str
    created_at: str | None
    updated_at: str | None
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
