"""Tests for the database initialization command."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from grimoire_api.repositories.migrations import (
    LATEST_SCHEMA_VERSION,
    SchemaInspection,
    SchemaMigrationError,
)

from scripts.init_database import (
    MIGRATION_PENDING_EXIT_CODE,
    NEW_DATABASE_EXIT_CODE,
    check_database_status,
    initialize_sqlite_only,
    migration_status,
)


@pytest.mark.asyncio
async def test_sqlite_initialization_runs_migrations(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """SQLite初期化が最新バージョンへの移行完了を表示する."""
    database = MagicMock()
    database.initialize_tables = AsyncMock()

    with patch("scripts.init_database.DatabaseConnection", return_value=database):
        assert await initialize_sqlite_only() is True

    database.initialize_tables.assert_awaited_once()
    assert "schema version 4" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_check_rejects_invalid_schema() -> None:
    """checkコマンドはスキーマ検証エラーを失敗として返す."""
    database = MagicMock()
    connection = AsyncMock()
    connection.__aenter__ = AsyncMock(return_value=connection)
    connection.__aexit__ = AsyncMock(return_value=False)
    database.connect.return_value = connection

    with (
        patch("scripts.init_database.DatabaseConnection", return_value=database),
        patch(
            "scripts.init_database.validate_database_schema",
            new=AsyncMock(side_effect=SchemaMigrationError("corrupt")),
        ),
    ):
        assert await check_database_status() is False


@pytest.mark.asyncio
async def test_migration_status_reports_new_database(tmp_path: Path) -> None:
    """DBファイルがない場合はバックアップ不要の専用終了コードを返す."""
    missing_path = str(tmp_path / "missing.db")
    with patch("scripts.init_database.settings.DATABASE_PATH", missing_path):
        assert await migration_status() == NEW_DATABASE_EXIT_CODE


@pytest.mark.asyncio
async def test_migration_status_requires_backup_for_legacy_database(
    tmp_path: Path,
) -> None:
    """既存旧DBにはバックアップ必須の終了コードを返す."""
    db_path = tmp_path / "legacy.db"
    db_path.touch()
    database = MagicMock()
    connection = AsyncMock()
    connection.__aenter__ = AsyncMock(return_value=connection)
    connection.__aexit__ = AsyncMock(return_value=False)
    database.connect.return_value = connection
    inspection = SchemaInspection(current_version=2, has_history=False, is_empty=False)

    with (
        patch("scripts.init_database.settings.DATABASE_PATH", str(db_path)),
        patch("scripts.init_database.DatabaseConnection", return_value=database),
        patch(
            "scripts.init_database.inspect_database_schema",
            new=AsyncMock(return_value=inspection),
        ),
    ):
        assert await migration_status() == MIGRATION_PENDING_EXIT_CODE

    assert inspection.pending_versions == tuple(range(3, LATEST_SCHEMA_VERSION + 1))


@pytest.mark.asyncio
async def test_migration_status_returns_success_for_latest_database(
    tmp_path: Path,
) -> None:
    """最新版DBでは移行もバックアップも不要と判定する."""
    db_path = tmp_path / "latest.db"
    db_path.touch()
    database = MagicMock()
    connection = AsyncMock()
    connection.__aenter__ = AsyncMock(return_value=connection)
    connection.__aexit__ = AsyncMock(return_value=False)
    database.connect.return_value = connection
    inspection = SchemaInspection(
        current_version=LATEST_SCHEMA_VERSION,
        has_history=True,
        is_empty=False,
    )

    with (
        patch("scripts.init_database.settings.DATABASE_PATH", str(db_path)),
        patch("scripts.init_database.DatabaseConnection", return_value=database),
        patch(
            "scripts.init_database.inspect_database_schema",
            new=AsyncMock(return_value=inspection),
        ),
    ):
        assert await migration_status() == 0


@pytest.mark.asyncio
async def test_migration_status_rejects_unknown_schema(tmp_path: Path) -> None:
    """未知スキーマの事前検査はデプロイ停止用の失敗を返す."""
    db_path = tmp_path / "unknown.db"
    db_path.touch()
    database = MagicMock()
    connection = AsyncMock()
    connection.__aenter__ = AsyncMock(return_value=connection)
    connection.__aexit__ = AsyncMock(return_value=False)
    database.connect.return_value = connection

    with (
        patch("scripts.init_database.settings.DATABASE_PATH", str(db_path)),
        patch("scripts.init_database.DatabaseConnection", return_value=database),
        patch(
            "scripts.init_database.inspect_database_schema",
            new=AsyncMock(side_effect=SchemaMigrationError("unknown")),
        ),
    ):
        assert await migration_status() == 1
