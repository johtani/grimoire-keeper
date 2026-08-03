"""Tests for representative search migration snapshots."""

import hashlib
import json
import tarfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.weaviate_1_38_migration import preflight, rollback_check
from tools.weaviate_1_38_migration.check_counts import verify_migration
from tools.weaviate_1_38_migration.preflight import run_preflight
from tools.weaviate_1_38_migration.rollback_check import run_rollback_check
from tools.weaviate_1_38_migration.search_snapshot import (
    capture_snapshot,
    compare_snapshots,
    load_queries,
    main,
)


@pytest.mark.asyncio
async def test_verify_migration_accepts_matching_counts() -> None:
    page_repo = MagicMock()
    page_repo.count_pages = AsyncMock(return_value=2)
    client = MagicMock()
    client.is_ready.return_value = True
    client.collections.exists.return_value = True
    page_collection = MagicMock()
    page_collection.aggregate.over_all.return_value.total_count = 2
    chunk_collection = MagicMock()
    chunk_collection.aggregate.over_all.return_value.total_count = 5
    client.collections.get.side_effect = [page_collection, chunk_collection]

    with (
        patch(
            "tools.weaviate_1_38_migration.check_counts.PageRepository",
            return_value=page_repo,
        ),
        patch(
            "tools.weaviate_1_38_migration.check_counts.weaviate.connect_to_local",
            return_value=client,
        ),
    ):
        result = await verify_migration()

    assert result == 0
    client.close.assert_called_once()


@pytest.mark.asyncio
async def test_verify_migration_rejects_page_count_mismatch() -> None:
    page_repo = MagicMock()
    page_repo.count_pages = AsyncMock(return_value=2)
    client = MagicMock()
    client.is_ready.return_value = True
    client.collections.exists.return_value = True
    page_collection = MagicMock()
    page_collection.aggregate.over_all.return_value.total_count = 1
    chunk_collection = MagicMock()
    chunk_collection.aggregate.over_all.return_value.total_count = 3
    client.collections.get.side_effect = [page_collection, chunk_collection]

    with (
        patch(
            "tools.weaviate_1_38_migration.check_counts.PageRepository",
            return_value=page_repo,
        ),
        patch(
            "tools.weaviate_1_38_migration.check_counts.weaviate.connect_to_local",
            return_value=client,
        ),
    ):
        result = await verify_migration()

    assert result == 1


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


def test_preflight_accepts_ready_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = tmp_path / "repo"
    data_root = tmp_path / "data"
    repo_root.mkdir()
    (repo_root / ".env").write_text("ENV_FILE=.env\n", encoding="utf-8")
    for directory in ("weaviate", "database", "json"):
        path = data_root / directory
        path.mkdir(parents=True)
        (path / "data").write_text("ready", encoding="utf-8")

    queries_path = tmp_path / "queries.json"
    queries_path.write_text(
        json.dumps(
            {
                "queries": [
                    {
                        "name": "content",
                        "type": "vector",
                        "query": "example",
                        "vector_name": "content_vector",
                        "limit": 3,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(_snapshot("before", [{"page_id": 1, "chunk_id": 0}])),
        encoding="utf-8",
    )

    monkeypatch.setattr(preflight.shutil, "which", lambda _: "/usr/bin/tool")
    monkeypatch.setattr(preflight, "_has_bws_token", lambda: True)
    monkeypatch.setattr(
        preflight.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=""),
    )
    monkeypatch.setattr(
        preflight.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(free=10 * preflight.GIB),
    )

    checks = run_preflight(
        repo_root,
        data_root,
        queries_path,
        baseline_path,
        1.0,
        "http://api/health",
        "http://weaviate/ready",
        url_checker=lambda _: (True, "HTTP 200"),
    )

    assert checks
    assert all(check.status == "PASS" for check in checks)


def test_preflight_rejects_populated_new_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = tmp_path / "repo"
    data_root = tmp_path / "data"
    repo_root.mkdir()
    (repo_root / ".env").touch()
    for directory in ("weaviate", "database", "json", "weaviate-1.38.8"):
        path = data_root / directory
        path.mkdir(parents=True)
        (path / "data").write_text("ready", encoding="utf-8")
    queries_path = tmp_path / "queries.json"
    queries_path.write_text(
        json.dumps(
            {"queries": [{"name": "content", "type": "vector", "query": "example"}]}
        ),
        encoding="utf-8",
    )
    baseline_path = tmp_path / "baseline.json"
    baseline = _snapshot("before", [])
    baseline["queries"][0]["request"] = {
        "name": "content",
        "type": "vector",
        "query": "example",
        "vector_name": "content_vector",
        "limit": 5,
    }
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    monkeypatch.setattr(preflight.shutil, "which", lambda _: "/usr/bin/tool")
    monkeypatch.setattr(preflight, "_has_bws_token", lambda: True)
    monkeypatch.setattr(
        preflight.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=""),
    )
    monkeypatch.setattr(
        preflight.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(free=10 * preflight.GIB),
    )

    checks = run_preflight(
        repo_root,
        data_root,
        queries_path,
        baseline_path,
        1.0,
        "http://api/health",
        "http://weaviate/ready",
        url_checker=lambda _: (True, "HTTP 200"),
    )

    new_data_check = next(
        check for check in checks if check.name == "empty new Weaviate data"
    )
    assert new_data_check.status == "FAIL"


def test_rollback_check_accepts_recorded_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".env").touch()
    old_data = tmp_path / "weaviate"
    old_data.mkdir()
    (old_data / "data").write_text("old", encoding="utf-8")
    backup_source = tmp_path / "backup-source"
    (backup_source / "database").mkdir(parents=True)
    (backup_source / "json").mkdir()
    (backup_source / "database" / "grimoire.db").write_text("db", encoding="utf-8")
    (backup_source / "json" / "1.json").write_text("{}", encoding="utf-8")
    backup = tmp_path / "backup.tar.gz"
    with tarfile.open(backup, "w:gz") as archive:
        archive.add(backup_source / "database", arcname="database")
        archive.add(backup_source / "json", arcname="json")
    info = tmp_path / "rollback.txt"
    info.write_text(
        "\n".join(
            [
                "api_commit=abc123",
                "weaviate_image=weaviate:1.33.1",
                f"weaviate_data={old_data}",
                f"sqlite_json_backup={backup}",
                f"sqlite_json_backup_sha256={hashlib.sha256(backup.read_bytes()).hexdigest()}",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        rollback_check.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0),
    )
    monkeypatch.setattr(rollback_check.shutil, "which", lambda _: "/usr/bin/tool")
    monkeypatch.setattr(rollback_check, "_has_bws_token", lambda: True)

    checks = run_rollback_check(info, repo_root)

    assert checks
    assert all(check.status == "PASS" for check in checks)


def test_rollback_check_rejects_incomplete_record(tmp_path: Path) -> None:
    info = tmp_path / "rollback.txt"
    info.write_text("api_commit=abc123\n", encoding="utf-8")

    checks = run_rollback_check(info, tmp_path)

    assert checks == [
        rollback_check.Check(
            "rollback info",
            "FAIL",
            "rollback info is missing keys: sqlite_json_backup, "
            "sqlite_json_backup_sha256, weaviate_data, weaviate_image",
        )
    ]
