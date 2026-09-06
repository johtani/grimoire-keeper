"""Tests for conservative URL canonicalization."""

import pytest
from grimoire_api.utils.url import canonicalize_url, find_url_collisions


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("HTTPS://Example.COM", "https://example.com/"),
        ("http://Example.com:80/a#section", "http://example.com/a"),
        ("https://Example.com:443/a", "https://example.com/a"),
        ("https://Example.com:8443/a", "https://example.com:8443/a"),
    ],
)
def test_canonicalize_url_applies_only_safe_structural_rules(
    url: str, expected: str
) -> None:
    assert canonicalize_url(url) == expected


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("https://example.com/a", "https://example.com/a/"),
        ("https://example.com/a?x=1&y=2", "https://example.com/a?y=2&x=1"),
        ("https://example.com/a?x=1&x=2", "https://example.com/a?x=2&x=1"),
        ("https://example.com/%7Euser", "https://example.com/~user"),
        ("http://example.com/a", "https://example.com/a"),
        ("https://www.example.com/a", "https://example.com/a"),
    ],
)
def test_canonicalize_url_preserves_content_sensitive_distinctions(
    first: str, second: str
) -> None:
    assert canonicalize_url(first) != canonicalize_url(second)


def test_canonicalize_url_removes_only_configured_tracking_parameters() -> None:
    url = "https://example.com/a?keep=1&utm_source=x&keep=2&utm%5Fcampaign=y"

    assert canonicalize_url(url, {"utm_source"}) == (
        "https://example.com/a?keep=1&keep=2&utm%5Fcampaign=y"
    )
    assert canonicalize_url(url, {"utm_source", "utm_campaign"}) == (
        "https://example.com/a?keep=1&keep=2"
    )


def test_find_url_collisions_is_deterministic_and_keeps_original_urls() -> None:
    rows = [
        (3, "https://other.example/a"),
        (1, "HTTPS://Example.COM:443/a#one"),
        (2, "https://example.com/a#two"),
    ]

    assert find_url_collisions(rows) == [
        {
            "dedupe_key": "https://example.com/a",
            "pages": [
                {"page_id": 1, "url": "HTTPS://Example.COM:443/a#one"},
                {"page_id": 2, "url": "https://example.com/a#two"},
            ],
        }
    ]
