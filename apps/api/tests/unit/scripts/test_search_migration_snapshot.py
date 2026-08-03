"""Tests for representative search migration snapshots."""

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.search_migration_snapshot import (
    capture_snapshot,
    compare_snapshots,
    load_queries,
    main,
)


def test_load_queries_accepts_all_search_types(tmp_path: Path) -> None:
    query_file = tmp_path / "queries.json"
    query_file.write_text(
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

    queries = load_queries(query_file)

    assert queries[0]["limit"] == 5
    assert queries[1]["keywords"] == ["AI"]


def test_load_queries_rejects_duplicate_names(tmp_path: Path) -> None:
    query_file = tmp_path / "queries.json"
    query_file.write_text(
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
        load_queries(query_file)


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
    assert calls[0] == (
        "http://api.example/api/v1/search",
        {"query": "example", "vector_name": "content_vector", "limit": 5},
        12.0,
    )
    assert calls[1] == (
        "http://api.example/api/v1/search/keywords?limit=10",
        ["AI"],
        12.0,
    )


def _snapshot(label: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "label": label,
        "queries": [
            {
                "name": "content",
                "request": {
                    "name": "content",
                    "type": "vector",
                    "query": "example",
                    "vector_name": "content_vector",
                    "limit": 3,
                },
                "response": {"total": len(results), "results": results},
            }
        ],
    }


def test_compare_snapshots_reports_missing_added_and_rank_changes() -> None:
    before = _snapshot(
        "before",
        [
            {"page_id": 1, "chunk_id": 1},
            {"page_id": 2, "chunk_id": 1},
            {"page_id": 3, "chunk_id": 1},
        ],
    )
    after = _snapshot(
        "after",
        [
            {"page_id": 2, "chunk_id": 1},
            {"page_id": 1, "chunk_id": 1},
            {"page_id": 4, "chunk_id": 1},
        ],
    )

    comparison = compare_snapshots(before, after)
    query = comparison["queries"][0]

    assert query["missing_results"] == ["page:3:chunk:1"]
    assert query["added_results"] == ["page:4:chunk:1"]
    assert query["overlap_ratio"] == 0.6667
    assert query["top_result_unchanged"] is False
    assert query["rank_changes"] == [
        {"result": "page:1:chunk:1", "before_rank": 1, "after_rank": 2},
        {"result": "page:2:chunk:1", "before_rank": 2, "after_rank": 1},
    ]


def test_compare_snapshots_rejects_changed_query() -> None:
    before = _snapshot("before", [{"page_id": 1, "chunk_id": 1}])
    after = _snapshot("after", [{"page_id": 1, "chunk_id": 1}])
    after["queries"][0]["request"]["query"] = "different"

    with pytest.raises(ValueError, match="request differs"):
        compare_snapshots(before, after)


def test_compare_command_fails_below_overlap_threshold(tmp_path: Path) -> None:
    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    output_path = tmp_path / "comparison.json"
    before_path.write_text(
        json.dumps(_snapshot("before", [{"page_id": 1, "chunk_id": 0}])),
        encoding="utf-8",
    )
    after_path.write_text(
        json.dumps(_snapshot("after", [{"page_id": 2, "chunk_id": 0}])),
        encoding="utf-8",
    )

    result = main(
        [
            "compare",
            "--before",
            str(before_path),
            "--after",
            str(after_path),
            "--output",
            str(output_path),
            "--fail-below-overlap",
            "0.8",
        ]
    )

    assert result == 1
    assert output_path.exists()
