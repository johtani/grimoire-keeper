"""Request models."""

from pydantic import BaseModel, HttpUrl


class ProcessUrlRequest(BaseModel):
    """URL処理リクエスト."""

    url: HttpUrl
    memo: str | None = None
    slack_channel: str | None = None
    slack_user: str | None = None


class SearchRequest(BaseModel):
    """検索リクエスト."""

    query: str
    limit: int = 5
    filters: dict | None = None
    vector_name: str = "content_vector"
    exclude_keywords: list[str] | None = None
