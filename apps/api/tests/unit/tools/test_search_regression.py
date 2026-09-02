"""Tests for the reusable search regression snapshot tool."""

import json
from pathlib import Path
from typing import Any

import pytest

from tools.search_regression.snapshot import (
    capture_snapshot,
    compare_snapshots,
    load_queries,
    main,
)


def test_load_queries_accepts_all_search_types(tmp_path: Path) -> None:
    path = tmp_path / "queries.json"
    path.write_text(
        json.dumps(
            {
                "queries": [
                    {
                        "name": "title",
                        "type": "vector",
                        "query": "example",
                        "vector_name": "title_vector",
                    },
                    {
                        "name": "keywords",
                        "type": "keywords",
                        "keywords": ["AI"],
                        "limit": 10,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    queries = load_queries(path)

    assert queries[0]["limit"] == 5
    assert queries[1]["keywords"] == ["AI"]


def test_load_queries_rejects_duplicate_names(tmp_path: Path) -> None:
    path = tmp_path / "queries.json"
    path.write_text(
        json.dumps(
            {
                "queries": [
                    {"name": "same", "type": "vector", "query": "one"},
                    {"name": "same", "type": "vector", "query": "two"},
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate query name"):
        load_queries(path)


def test_capture_snapshot_calls_vector_and_keyword_endpoints() -> None:
    calls: list[tuple[str, Any, float]] = []

    def requester(url: str, payload: Any, timeout: float) -> dict[str, Any]:
        calls.append((url, payload, timeout))
        return {"results": [], "total": 0, "query": "example"}

    snapshot = capture_snapshot(
        [
            {
                "name": "content",
                "type": "vector",
                "query": "example",
                "vector_name": "content_vector",
                "limit": 5,
            },
            {
                "name": "keywords",
                "type": "keywords",
                "keywords": ["AI"],
                "limit": 10,
            },
        ],
        "http://api.example/",
        "before",
        12.0,
        requester=requester,
    )

    assert snapshot["label"] == "before"
    assert calls == [
        (
            "http://api.example/api/v1/search",
            {"query": "example", "vector_name": "content_vector", "limit": 5},
            12.0,
        ),
        (
            "http://api.example/api/v1/search/keywords",
            {"keywords": ["AI"], "limit": 10},
            12.0,
        ),
    ]


def _snapshot(label: str, page_ids: list[int]) -> dict[str, Any]:
    request = {
        "name": "content",
        "type": "vector",
        "query": "example",
        "vector_name": "content_vector",
        "limit": 3,
    }
    results = [{"page_id": page_id, "chunk_id": 1} for page_id in page_ids]
    return {
        "schema_version": 1,
        "label": label,
        "queries": [
            {
                "name": "content",
                "request": request,
                "response": {"total": len(results), "results": results},
            }
        ],
    }


def test_compare_snapshots_reports_result_and_rank_changes() -> None:
    comparison = compare_snapshots(
        _snapshot("before", [1, 2, 3]), _snapshot("after", [2, 1, 4])
    )
    query = comparison["queries"][0]

    assert query["missing_results"] == ["page:3:chunk:1"]
    assert query["added_results"] == ["page:4:chunk:1"]
    assert query["overlap_ratio"] == 0.6667
    assert query["top_result_unchanged"] is False
    assert query["rank_changes"] == [
        {"result": "page:1:chunk:1", "before_rank": 1, "after_rank": 2},
        {"result": "page:2:chunk:1", "before_rank": 2, "after_rank": 1},
    ]


def test_compare_snapshots_compares_keyword_results_by_unique_page() -> None:
    request = {
        "name": "keyword",
        "type": "keywords",
        "keywords": ["example"],
        "limit": 5,
    }

    def keyword_snapshot(label: str, results: list[dict[str, int]]) -> dict:
        return {
            "schema_version": 1,
            "label": label,
            "queries": [
                {
                    "name": "keyword",
                    "request": request,
                    "response": {"total": len(results), "results": results},
                }
            ],
        }

    comparison = compare_snapshots(
        keyword_snapshot(
            "before",
            [
                {"page_id": 2, "chunk_id": 0},
                {"page_id": 2, "chunk_id": 1},
                {"page_id": 2, "chunk_id": 2},
            ],
        ),
        keyword_snapshot(
            "after",
            [
                {"page_id": 2, "chunk_id": 0},
                {"page_id": 16, "chunk_id": 0},
            ],
        ),
    )
    query = comparison["queries"][0]

    assert query["comparison_unit"] == "page"
    assert query["before_results"] == ["page:2"]
    assert query["after_results"] == ["page:2", "page:16"]
    assert query["missing_results"] == []
    assert query["added_results"] == ["page:16"]
    assert query["overlap_ratio"] == 1.0
    assert query["top_result_unchanged"] is True


def test_compare_snapshots_rejects_changed_query() -> None:
    before = _snapshot("before", [1])
    after = _snapshot("after", [1])
    after["queries"][0]["request"]["query"] = "different"

    with pytest.raises(ValueError, match="request differs"):
        compare_snapshots(before, after)


def test_compare_command_fails_below_overlap_threshold(tmp_path: Path) -> None:
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    output = tmp_path / "comparison.json"
    before.write_text(json.dumps(_snapshot("before", [1])), encoding="utf-8")
    after.write_text(json.dumps(_snapshot("after", [2])), encoding="utf-8")

    result = main(
        [
            "compare",
            "--before",
            str(before),
            "--after",
            str(after),
            "--output",
            str(output),
            "--fail-below-overlap",
            "0.8",
        ]
    )

    assert result == 1
    assert output.exists()
