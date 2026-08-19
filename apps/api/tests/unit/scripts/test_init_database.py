"""Tests for the database initialization command."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from grimoire_api.repositories.migrations import SchemaMigrationError

from scripts.init_database import check_database_status, initialize_sqlite_only


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
