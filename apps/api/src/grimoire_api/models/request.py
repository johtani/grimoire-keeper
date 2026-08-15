"""Request models."""

import re

from pydantic import BaseModel, HttpUrl, field_validator

from .database import ReprocessStartStep


class ProcessUrlRequest(BaseModel):
    """URL処理リクエスト."""

    url: HttpUrl
    memo: str | None = None
    slack_channel: str | None = None
    slack_user: str | None = None

    @field_validator("url", mode="before")
    @classmethod
    def reject_malformed_url_suffix(cls, value: object) -> object:
        """Slack マークアップ由来の不正な末尾を正規化前に拒否する."""
        if isinstance(value, str) and re.search(r"(?:>|%3e)$", value, re.IGNORECASE):
            raise ValueError("URL must not end with '>' or '%3E'")
        return value


class RetryAllRequest(BaseModel):
    """一括再処理リクエスト."""

    max_retries: int | None = None
    delay_seconds: int = 1


class ReprocessRequest(BaseModel):
    """再処理リクエスト."""

    from_step: ReprocessStartStep = ReprocessStartStep.AUTO


class UpdatePageUrlRequest(BaseModel):
    """楽観ロック付きページURL更新リクエスト."""

    current_url: str
    new_url: HttpUrl

    @field_validator("new_url", mode="before")
    @classmethod
    def reject_malformed_url_suffix(cls, value: object) -> object:
        if isinstance(value, str) and re.search(r"(?:>|%3e)$", value, re.IGNORECASE):
            raise ValueError("URL must not end with '>' or '%3E'")
        return value


class SearchRequest(BaseModel):
    """検索リクエスト."""

    query: str
    limit: int = 5
    filters: dict | None = None
    vector_name: str = "content_vector"
    exclude_keywords: list[str] | None = None
