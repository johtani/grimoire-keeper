"""Request models."""

import re
from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    field_validator,
    model_validator,
)

from .database import ReprocessStartStep


class ProcessUrlRequest(BaseModel):
    """URL処理リクエスト."""

    model_config = ConfigDict(extra="forbid")

    url: HttpUrl
    memo: str | None = None

    @field_validator("url", mode="before")
    @classmethod
    def reject_malformed_url_suffix(cls, value: object) -> object:
        """Slack マークアップ由来の不正な末尾を正規化前に拒否する."""
        if isinstance(value, str) and re.search(r"(?:>|%3e)$", value, re.IGNORECASE):
            raise ValueError("URL must not end with '>' or '%3E'")
        return value


class RetryAllRequest(BaseModel):
    """一括再処理リクエスト."""

    model_config = ConfigDict(extra="forbid")

    max_retries: int | None = Field(default=None, ge=1, le=1000)


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


SearchKeyword = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


class SearchFilters(BaseModel):
    """検索対象を絞り込むフィルター."""

    model_config = ConfigDict(extra="forbid")

    url: (
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2048)
        ]
        | None
    ) = None
    keywords: list[SearchKeyword] | None = Field(
        default=None, min_length=1, max_length=20
    )
    date_from: datetime | None = None
    date_to: datetime | None = None

    @model_validator(mode="after")
    def validate_date_range(self) -> "SearchFilters":
        """開始日時が終了日時より後の範囲を拒否する."""
        if self.date_from is not None:
            self.date_from = self._as_utc(self.date_from)
        if self.date_to is not None:
            self.date_to = self._as_utc(self.date_to)
        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_from > self.date_to
        ):
            raise ValueError("date_from must not be later than date_to")
        return self

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        """タイムゾーンなしの入力を UTC として比較可能にする."""
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class SearchRequest(BaseModel):
    """検索リクエスト."""

    model_config = ConfigDict(extra="forbid")

    query: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
    ]
    limit: int = Field(default=5, ge=1, le=100)
    filters: SearchFilters | None = None
    vector_name: Literal["content_vector", "title_vector", "memo_vector"] = (
        "content_vector"
    )
    exclude_keywords: list[SearchKeyword] | None = Field(
        default=None, min_length=1, max_length=20
    )
