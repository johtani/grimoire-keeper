"""Test database initialization."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest
from grimoire_api.repositories.database import DatabaseConnection


class TestDatabaseInitialization:
    """DatabaseConnection.initialize_tables() のテストクラス."""

    @pytest.mark.asyncio
    async def test_indexes_created(self, temp_db: DatabaseConnection) -> None:
        """インデックスが正しく作成されることを確認."""
        rows = await temp_db.fetch_all(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
        index_names = {row["name"] for row in rows}

        assert "idx_process_logs_page_id" in index_names
        assert "idx_process_logs_status" in index_names
        assert "idx_pages_last_success_step" in index_names

    @pytest.mark.asyncio
    async def test_indexes_idempotent(self, temp_db: DatabaseConnection) -> None:
        """initialize_tables() を再度呼び出しても例外が発生しないことを確認."""
        await temp_db.initialize_tables()

        rows = await temp_db.fetch_all(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
        index_names = {row["name"] for row in rows}

        assert "idx_process_logs_page_id" in index_names
        assert "idx_process_logs_status" in index_names
        assert "idx_pages_last_success_step" in index_names

    @pytest.mark.asyncio
    async def test_migration_duplicate_column_error_is_ignored(self) -> None:
        """duplicate column エラーが発生しても例外にならないことを確認."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            db = DatabaseConnection(db_path)
            duplicate_error = aiosqlite.OperationalError(
                "duplicate column name: last_success_step"
            )
            with patch("aiosqlite.connect") as mock_connect:
                mock_conn = AsyncMock()
                mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
                mock_conn.__aexit__ = AsyncMock(return_value=False)
                mock_conn.execute = AsyncMock(
                    side_effect=[
                        None,  # PRAGMA journal_mode=WAL
                        None,  # PRAGMA synchronous=NORMAL
                        None,  # PRAGMA cache_size=10000
                        None,  # PRAGMA busy_timeout=30000
                        None,  # pages_table
                        None,  # process_logs_table
                        duplicate_error,  # migration_query → duplicate column
                        None,  # idx_process_logs_page_id
                        None,  # idx_process_logs_status
                        None,  # idx_pages_last_success_step
                    ]
                )
                mock_connect.return_value = mock_conn
                await db.initialize_tables()  # 例外が発生しないことを確認
        finally:
            Path(db_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_migration_other_operational_error_is_raised(self) -> None:
        """duplicate column 以外の OperationalError は再 raise されることを確認."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            db = DatabaseConnection(db_path)
            other_error = aiosqlite.OperationalError("no such table: pages")
            with patch("aiosqlite.connect") as mock_connect:
                mock_conn = AsyncMock()
                mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
                mock_conn.__aexit__ = AsyncMock(return_value=False)
                mock_conn.execute = AsyncMock(
                    side_effect=[
                        None,  # PRAGMA journal_mode=WAL
                        None,  # PRAGMA synchronous=NORMAL
                        None,  # PRAGMA cache_size=10000
                        None,  # PRAGMA busy_timeout=30000
                        None,  # pages_table
                        None,  # process_logs_table
                        other_error,  # migration_query → other error
                    ]
                )
                mock_connect.return_value = mock_conn
                with pytest.raises(aiosqlite.OperationalError, match="no such table"):
                    await db.initialize_tables()
        finally:
            Path(db_path).unlink(missing_ok=True)
