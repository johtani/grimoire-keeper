"""Validated models for responses received from external services."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator


class FetchedDocument(BaseModel):
    """Jina Reader response normalized for use inside the application."""

    model_config = ConfigDict(extra="forbid")

    title: StrictStr
    content: StrictStr
    language: StrictStr | None = None
    source_url: StrictStr
    raw_response: dict[str, Any]

    @field_validator("title", "content", "source_url")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value.strip()

    @field_validator("language")
    @classmethod
    def normalize_language(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @classmethod
    def from_jina_response(
        cls, response: dict[str, Any], *, source_url: str
    ) -> "FetchedDocument":
        """Validate and normalize a raw Jina Reader response."""
        data = response.get("data")
        if not isinstance(data, dict):
            raise ValueError("data must be an object")

        language = next(
            (
                data.get(field)
                for field in (
                    "language",
                    "lang",
                    "detected_language",
                    "content_language",
                )
                if data.get(field) is not None
            ),
            None,
        )
        return cls.model_validate(
            {
                "title": data.get("title"),
                "content": data.get("content"),
                "language": language,
                "source_url": source_url,
                "raw_response": response,
            }
        )


class PartialSummaryResult(BaseModel):
    """Validated intermediate summary returned by the LLM."""

    summary: StrictStr = Field(max_length=2000)

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("summary must not be empty")
        return normalized


class SummaryResult(PartialSummaryResult):
    """Validated final summary and keywords returned by the LLM."""

    keywords: list[StrictStr] = Field(min_length=1, max_length=20)

    @field_validator("keywords", mode="before")
    @classmethod
    def normalize_keywords(cls, value: Any) -> list[str]:
        if not isinstance(value, list):
            raise ValueError("keywords must be a list")

        normalized: list[str] = []
        seen: set[str] = set()
        for keyword in value:
            if not isinstance(keyword, str):
                raise ValueError("keywords must contain only strings")
            keyword = keyword.strip()
            if not keyword:
                raise ValueError("keywords must not contain empty strings")
            if keyword not in seen:
                normalized.append(keyword)
                seen.add(keyword)
        return normalized
