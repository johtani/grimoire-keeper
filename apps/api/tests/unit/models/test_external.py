"""Tests for validated external response models."""

from typing import Any

import pytest
from grimoire_api.models.external import FetchedDocument, SummaryResult
from pydantic import ValidationError


def _jina_response(**overrides: Any) -> dict[str, Any]:
    data = {"title": "Title", "content": "Content", **overrides}
    return {"code": 200, "data": data, "extra": {"preserved": True}}


@pytest.mark.parametrize("field", ["title", "content"])
def test_fetched_document_rejects_missing_required_field(field: str) -> None:
    response = _jina_response()
    del response["data"][field]

    with pytest.raises(ValidationError):
        FetchedDocument.from_jina_response(response, source_url="https://example.com")


@pytest.mark.parametrize("field", ["title", "content"])
@pytest.mark.parametrize("value", ["", "   ", 123, None])
def test_fetched_document_rejects_invalid_required_text(field: str, value: Any) -> None:
    with pytest.raises(ValidationError):
        FetchedDocument.from_jina_response(
            _jina_response(**{field: value}), source_url="https://example.com"
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("language", "ja"),
        ("lang", "en"),
        ("detected_language", "fr"),
        ("content_language", "de"),
    ],
)
def test_fetched_document_normalizes_language_candidates(
    field: str, value: str
) -> None:
    response = _jina_response(**{field: value})

    document = FetchedDocument.from_jina_response(
        response, source_url="https://requested.example"
    )

    assert document.language == value
    assert document.source_url == "https://requested.example"
    assert document.raw_response == response


def test_summary_result_normalizes_keywords_in_order() -> None:
    result = SummaryResult(
        summary="  Summary  ", keywords=[" first ", "second", "first"]
    )

    assert result.summary == "Summary"
    assert result.keywords == ["first", "second"]


@pytest.mark.parametrize("summary", ["", "  ", "x" * 2001, 123])
def test_summary_result_rejects_invalid_summary(summary: Any) -> None:
    with pytest.raises(ValidationError):
        SummaryResult(summary=summary, keywords=["keyword"])


@pytest.mark.parametrize(
    "keywords",
    [
        [],
        [f"keyword-{index}" for index in range(21)],
        [""],
        ["   "],
        [1],
        "keyword",
    ],
)
def test_summary_result_rejects_invalid_keywords(keywords: Any) -> None:
    with pytest.raises(ValidationError):
        SummaryResult(summary="Summary", keywords=keywords)
