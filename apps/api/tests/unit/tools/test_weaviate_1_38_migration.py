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


def test_migration_uses_repair_pending_report_for_reindex_and_counts() -> None:
    """再索引と件数検証が本番永続領域の同じレポートを共有する."""
    migrate_script = (
        Path(__file__).parents[5] / "tools" / "weaviate_1_38_migration" / "migrate.sh"
    ).read_text(encoding="utf-8")

    assert 'DATA_ROOT="/opt/grimoire-keeper-data"' in migrate_script
    assert 'MIGRATION_DIR="${DATA_ROOT}/migration"' in migrate_script
    assert 'MIGRATION_DIR="${PROJECT_ROOT}/data/migration"' not in migrate_script
    assert 'sudo mkdir -p "${MIGRATION_DIR}"' in migrate_script
    assert 'sudo chown -R "${APP_UID}:${APP_GID}" "${MIGRATION_DIR}"' in migrate_script
    assert 'sudo chmod 0750 "${MIGRATION_DIR}"' in migrate_script
    assert migrate_script.count('"${MIGRATION_DIR}:/migration"') == 3
    assert (
        migrate_script.count(
            '--repair-pending-output "${CONTAINER_REPAIR_PENDING_REPORT}"'
        )
        == 2
    )
    assert (
        '--repair-pending-report "${CONTAINER_REPAIR_PENDING_REPORT}"' in migrate_script
    )


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
async def test_verify_migration_uses_repair_pending_target_count(
    tmp_path: Path,
) -> None:
    """修復待ちを除いた移行対象件数でWeaviateを検証する."""
    report = tmp_path / "repair-pending.json"
    report.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "completed_pages": 2,
                "scanned_pages": 2,
                "migration_targets": 1,
                "repair_pending_count": 1,
                "repair_pending": [{"page_id": 56, "reasons": []}],
            }
        ),
        encoding="utf-8",
    )
    page_repo = MagicMock()
    page_repo.count_completed_pages = AsyncMock(return_value=2)
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
            "tools.weaviate_1_38_migration.check_counts.MigrationPageRepository",
            return_value=page_repo,
        ),
        patch(
            "tools.weaviate_1_38_migration.check_counts.weaviate.connect_to_local",
            return_value=client,
        ),
    ):
        result = await verify_migration(report)

    assert result == 0
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
    (data_root / "json" / "1.json").write_text(
        json.dumps(
            {
                "code": 200,
                "status": 20000,
                "data": {
                    "title": "title",
                    "content": "stored content",
                    "httpStatus": 200,
                },
            }
        ),
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
    assert coverage.status == "WARN"
    assert "page IDs: 1" in coverage.detail


def test_preflight_rejects_completed_page_json_without_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """本文が空のJina JSONを移行前に検出する."""
    repo_root, data_root = _prepare_preflight(tmp_path, monkeypatch)
    queries_path, baseline_path = _write_queries_and_baseline(tmp_path)
    (data_root / "json" / "1.json").write_text(
        json.dumps({"data": {"title": "title", "content": ""}}),
        encoding="utf-8",
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

    validity = next(
        check for check in checks if check.name == "completed page JSON validity"
    )
    assert validity.status == "WARN"
    assert "page IDs: 1" in validity.detail


def test_preflight_rejects_jina_http_error_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """本文文字列があってもJinaのHTTPエラーレスポンスを拒否する."""
    repo_root, data_root = _prepare_preflight(tmp_path, monkeypatch)
    queries_path, baseline_path = _write_queries_and_baseline(tmp_path)
    (data_root / "json" / "1.json").write_text(
        json.dumps(
            {
                "data": {
                    "title": "",
                    "content": "404 error page content",
                    "httpStatus": 404,
                    "httpStatusText": "Not Found",
                }
            }
        ),
        encoding="utf-8",
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

    validity = next(
        check for check in checks if check.name == "completed page JSON validity"
    )
    assert validity.status == "WARN"
    assert "page IDs: 1" in validity.detail


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


@pytest.mark.parametrize("key", [None, "", " \t\n", "test-embedding-key"])
def test_migration_checks_bws_key_before_mutations(
    tmp_path: Path, key: str | None
) -> None:
    """BWS子プロセスのキーを検証し、値を出力せず停止作業前に失敗する。"""
    import subprocess

    script = (
        Path(__file__).parents[5] / "tools/weaviate_1_38_migration/migrate.sh"
    ).read_text()
    # 実際の事前検証部分だけを実行し、本番データへの操作を避ける。
    preflight = script.split('if [ ! -d "${OLD_WEAVIATE_DATA}" ]; then', 1)[0]
    assert "sudo " not in preflight
    assert "docker compose" not in preflight
    (tmp_path / ".env").touch()
    bws = tmp_path / "bws"
    bws.write_text('#!/bin/sh\nshift 2\nexec "$@"\n')
    bws.chmod(0o755)
    env = {"PATH": f"{tmp_path}:/usr/bin:/bin", "BWS_ACCESS_TOKEN": "test-token"}
    if key is not None:
        env["GRIMOIRE_KEEPER_OPENAI_API_KEY"] = key
    result = subprocess.run(
        ["bash", "-c", preflight],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == (0 if key == "test-embedding-key" else 1)
    if result.returncode:
        assert "GRIMOIRE_KEEPER_OPENAI_API_KEY が必要です" in result.stdout
    else:
        assert result.stdout == ""
    assert "test-embedding-key" not in result.stdout + result.stderr
    assert "test-token" not in result.stdout + result.stderr


def test_migration_reindex_commands_inherit_api_environment() -> None:
    """移行の再インデックス・件数確認がBWS配下のAPIサービスを使う。"""
    import shlex

    script = (
        (Path(__file__).parents[5] / "tools/weaviate_1_38_migration/migrate.sh")
        .read_text()
        .replace("\\\n", " ")
    )
    commands = [
        shlex.split(line)
        for line in script.splitlines()
        if line.startswith("bws run -- docker compose") and " run --rm " in line
    ]
    assert len(commands) == 3
    for command in commands:
        assert command[:3] == ["bws", "run", "--"]
        assert command[command.index("api") + 1] == "python"
        assert "--env" not in command and "-e" not in command
    assert sum("tools.weaviate_1_38_migration.reindex" in cmd for cmd in commands) == 2
