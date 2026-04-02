"""Test database initialization."""

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
