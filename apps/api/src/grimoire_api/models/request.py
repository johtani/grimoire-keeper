"""Request models."""

from pydantic import BaseModel, HttpUrl

from .database import ReprocessStartStep


class ProcessUrlRequest(BaseModel):
    """URL処理リクエスト."""

    url: HttpUrl
    memo: str | None = None
    slack_channel: str | None = None
    slack_user: str | None = None


class RetryAllRequest(BaseModel):
    """一括再処理リクエスト."""

    max_retries: int | None = None
    delay_seconds: int = 1


class ReprocessRequest(BaseModel):
    """再処理リクエスト."""

    from_step: ReprocessStartStep = ReprocessStartStep.AUTO


class SearchRequest(BaseModel):
    """検索リクエスト."""

    query: str
    limit: int = 5
    filters: dict | None = None
    vector_name: str = "content_vector"
    exclude_keywords: list[str] | None = None
