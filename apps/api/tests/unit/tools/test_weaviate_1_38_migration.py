"""Tests for the temporary Weaviate 1.38 migration tools."""

import hashlib
import json
import sqlite3
import tarfile
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest
from grimoire_api.repositories.database import DatabaseConnection

from tools.weaviate_1_38_migration import preflight, rollback_check
from tools.weaviate_1_38_migration.check_counts import verify_migration
from tools.weaviate_1_38_migration.page_repository import MigrationPageRepository
from tools.weaviate_1_38_migration.preflight import run_preflight
from tools.weaviate_1_38_migration.rollback_check import run_rollback_check


def test_migration_compose_allows_sqlite_wal_locking() -> None:
    """DBはWAL用に書込可能でマウントし、他の本番データはread-onlyに保つ."""
    compose_path = (
        Path(__file__).parents[5]
        / "tools"
        / "weaviate_1_38_migration"
        / "docker-compose.yml"
    )
    compose = compose_path.read_text(encoding="utf-8")

    assert "/opt/grimoire-keeper-data/database:/data\n" in compose
    assert "/opt/grimoire-keeper-data/database:/data:ro" not in compose
    assert "/opt/grimoire-keeper-data/json:/app/apps/api/data/json:ro" in compose


def test_read_only_database_commands_run_as_root() -> None:
    """root所有のWALを扱うDB参照コマンドだけrootで実行する."""
    run_script = (
        Path(__file__).parents[5] / "tools" / "weaviate_1_38_migration" / "run.sh"
    ).read_text(encoding="utf-8")

    assert run_script.count("MIGRATION_UID=0 MIGRATION_GID=0 run_tool") == 3


def test_migration_backup_handles_root_owned_json_atomically() -> None:
    """root所有JSONをsudoで読み、完成したバックアップだけを公開する."""
    migrate_script = (
        Path(__file__).parents[5] / "tools" / "weaviate_1_38_migration" / "migrate.sh"
    ).read_text(encoding="utf-8")

    sudo_tar = 'sudo tar -C "${DATA_ROOT}" -czf "${BACKUP_TEMP}" database json'
    chown = 'sudo chown "${USER}:${USER}" "${BACKUP_TEMP}"'
    publish = 'mv "${BACKUP_TEMP}" "${BACKUP_FILE}"'
    assert sudo_tar in migrate_script
    assert chown in migrate_script
    assert publish in migrate_script
    assert migrate_script.index(sudo_tar) < migrate_script.index(chown)
    assert migrate_script.index(chown) < migrate_script.index(publish)


@pytest.mark.asyncio
@pytest.mark.parametrize("page_count, expected", [(2, 0), (1, 1)])
async def test_verify_migration_page_counts(page_count: int, expected: int) -> None:
    page_repo = MagicMock()
    page_repo.count_completed_pages = AsyncMock(return_value=2)
    client = MagicMock()
    client.is_ready.return_value = True
    client.collections.exists.return_value = True
    page_collection = MagicMock()
    page_collection.aggregate.over_all.return_value.total_count = page_count
    chunk_collection = MagicMock()
    chunk_collection.aggregate.over_all.return_value.total_count = 5
    client.collections.get.side_effect = [page_collection, chunk_collection]

    with (
        patch(
            "tools.weaviate_1_38_migration.check_counts.MigrationPageRepository",
            return_value=page_repo,
        ),
        patch(
            "tools.weaviate_1_38_migration.check_counts.weaviate.connect_to_local",
            return_value=client,
        ),
    ):
        result = await verify_migration()

    assert result == expected
    client.close.assert_called_once()


@pytest.mark.asyncio
async def test_migration_repository_reads_legacy_pages_schema(tmp_path: Path) -> None:
    """status列のない旧DBから完了ページだけを取得する."""
    db_path = tmp_path / "legacy.db"
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            """CREATE TABLE pages (
                id INTEGER PRIMARY KEY, url TEXT, title TEXT, memo TEXT,
                summary TEXT, keywords TEXT, weaviate_id TEXT,
                last_success_step TEXT, created_at TEXT, updated_at TEXT
            )"""
        )
        await conn.executemany(
            "INSERT INTO pages VALUES (?, ?, ?, NULL, ?, '[]', ?, ?, ?, ?)",
            [
                (
                    1,
                    "https://completed.example.com",
                    "completed",
                    "summary",
                    "uuid-1",
                    "completed",
                    "2026-01-01T00:00:00",
                    "2026-01-01T00:00:00",
                ),
                (
                    2,
                    "https://failed.example.com",
                    "failed",
                    None,
                    None,
                    "downloaded",
                    "2026-01-01T00:00:00",
                    "2026-01-01T00:00:00",
                ),
            ],
        )
        await conn.commit()

    repository = MigrationPageRepository(
        DatabaseConnection(str(db_path), read_only=True)
    )

    assert await repository.count_completed_pages() == 1
    pages = await repository.get_completed_pages(limit=10)
    assert [page.id for page in pages] == [1]
    assert pages[0].status.value == "succeeded"
    assert (await repository.get_page(1)) == pages[0]


def _write_queries_and_baseline(
    tmp_path: Path, *, with_results: bool = True
) -> tuple[Path, Path]:
    request = {
        "name": "content",
        "type": "vector",
        "query": "example",
        "vector_name": "content_vector",
        "limit": 3,
    }
    queries_path = tmp_path / "queries.json"
    queries_path.write_text(json.dumps({"queries": [request]}), encoding="utf-8")
    baseline_path = tmp_path / "baseline.json"
    results = [{"page_id": 1, "chunk_id": 0}] if with_results else []
    baseline_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "queries": [
                    {
                        "name": "content",
                        "request": request,
                        "response": {"total": len(results), "results": results},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return queries_path, baseline_path


def _prepare_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, populate_new: bool = False
) -> tuple[Path, Path]:
    repo_root = tmp_path / "repo"
    data_root = tmp_path / "data"
    repo_root.mkdir()
    (repo_root / ".env").touch()
    directories = ["weaviate", "database", "json"]
    if populate_new:
        directories.append("weaviate-1.38.8")
    for directory in directories:
        path = data_root / directory
        path.mkdir(parents=True)
        (path / "data").write_text("ready", encoding="utf-8")
    with closing(sqlite3.connect(data_root / "database" / "grimoire.db")) as connection:
        connection.execute(
            """CREATE TABLE pages (
                id INTEGER PRIMARY KEY, url TEXT, title TEXT, memo TEXT,
                summary TEXT, keywords TEXT, weaviate_id TEXT,
                last_success_step TEXT, created_at TEXT, updated_at TEXT
            )"""
        )
        connection.execute(
            """INSERT INTO pages VALUES (
                1, 'https://example.com', 'title', NULL, 'summary', '[]',
                'uuid-1', 'completed', '2026-01-01T00:00:00',
                '2026-01-01T00:00:00'
            )"""
        )
        connection.commit()
    (data_root / "json" / "1.json").write_text("{}", encoding="utf-8")
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
    return repo_root, data_root


def test_preflight_accepts_ready_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root, data_root = _prepare_preflight(tmp_path, monkeypatch)
    queries_path, baseline_path = _write_queries_and_baseline(tmp_path)

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
    repo_root, data_root = _prepare_preflight(tmp_path, monkeypatch, populate_new=True)
    queries_path, baseline_path = _write_queries_and_baseline(tmp_path)

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

    check = next(item for item in checks if item.name == "empty new Weaviate data")
    assert check.status == "FAIL"


def test_preflight_rejects_missing_completed_page_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """成功済みページのJina JSON不足を移行前に検出する."""
    repo_root, data_root = _prepare_preflight(tmp_path, monkeypatch)
    queries_path, baseline_path = _write_queries_and_baseline(tmp_path)
    (data_root / "json" / "1.json").unlink()

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

    coverage = next(
        check for check in checks if check.name == "completed page JSON coverage"
    )
    assert coverage.status == "FAIL"
    assert "page IDs: 1" in coverage.detail


def test_containerized_preflight_skips_host_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root, data_root = _prepare_preflight(tmp_path, monkeypatch)
    queries_path, baseline_path = _write_queries_and_baseline(tmp_path)
    (repo_root / ".env").unlink()
    monkeypatch.setattr(preflight.shutil, "which", lambda _: None)
    monkeypatch.setattr(preflight, "_has_bws_token", lambda: False)

    checks = run_preflight(
        repo_root,
        data_root,
        queries_path,
        baseline_path,
        1.0,
        "http://api/health",
        "http://weaviate/ready",
        url_checker=lambda _: (True, "HTTP 200"),
        check_host_environment=False,
    )

    names = {check.name for check in checks}
    assert "repository .env" not in names
    assert "docker command" not in names
    assert all(check.status == "PASS" for check in checks)


def test_rollback_check_accepts_recorded_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".env").touch()
    old_data = tmp_path / "weaviate"
    old_data.mkdir()
    (old_data / "data").write_text("old", encoding="utf-8")
    source = tmp_path / "source"
    (source / "database").mkdir(parents=True)
    (source / "json").mkdir()
    backup = tmp_path / "backup.tar.gz"
    with tarfile.open(backup, "w:gz") as archive:
        archive.add(source / "database", arcname="database")
        archive.add(source / "json", arcname="json")
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


def test_containerized_rollback_uses_host_verified_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old_data = tmp_path / "weaviate"
    old_data.mkdir()
    (old_data / "data").touch()
    source = tmp_path / "source"
    (source / "database").mkdir(parents=True)
    (source / "json").mkdir()
    backup = tmp_path / "backup.tar.gz"
    with tarfile.open(backup, "w:gz") as archive:
        archive.add(source / "database", arcname="database")
        archive.add(source / "json", arcname="json")
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
        lambda *args, **kwargs: pytest.fail("git must be checked by the host wrapper"),
    )

    checks = run_rollback_check(
        info,
        tmp_path,
        check_host_environment=False,
        verified_api_commit="abc123",
    )

    assert checks
    assert all(check.status == "PASS" for check in checks)
    assert "docker command" not in {check.name for check in checks}
