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

                async def execute(query: str, *args: object) -> None:
                    if "ADD COLUMN last_success_step" in query:
                        raise duplicate_error

                mock_conn.execute = AsyncMock(side_effect=execute)
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

                async def execute(query: str, *args: object) -> None:
                    if "ADD COLUMN last_success_step" in query:
                        raise other_error

                mock_conn.execute = AsyncMock(side_effect=execute)
                mock_connect.return_value = mock_conn
                with pytest.raises(aiosqlite.OperationalError, match="no such table"):
                    await db.initialize_tables()
        finally:
            Path(db_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_legacy_pages_are_backfilled_idempotently(self) -> None:
        """旧スキーマの完了・未完了ページを現在状態へ一度だけ移行する."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            async with aiosqlite.connect(db_path) as conn:
                await conn.execute(
                    """CREATE TABLE pages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL, memo TEXT, summary TEXT, keywords TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    weaviate_id TEXT, last_success_step TEXT)"""
                )
                await conn.execute(
                    """INSERT INTO pages (url, title, summary, weaviate_id)
                    VALUES ('https://done.example.com', 'done', 'summary', 'uuid')"""
                )
                await conn.execute(
                    """INSERT INTO pages (url, title)
                    VALUES ('https://lost.example.com', 'lost')"""
                )
                await conn.commit()

            db = DatabaseConnection(db_path)
            await db.initialize_tables()
            await db.initialize_tables()

            rows = await db.fetch_all("SELECT url, status FROM pages ORDER BY id")
            assert [(row["url"], row["status"]) for row in rows] == [
                ("https://done.example.com", "succeeded"),
                ("https://lost.example.com", "failed"),
            ]
            jobs = await db.fetch_one("SELECT COUNT(*) AS count FROM jobs")
            assert jobs is not None and jobs["count"] == 0
        finally:
            Path(db_path).unlink(missing_ok=True)
