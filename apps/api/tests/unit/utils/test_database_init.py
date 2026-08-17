"""Database initialization utility tests."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from grimoire_api.utils.database_init import (
    ensure_database_initialized,
    reset_database,
)


@pytest.mark.asyncio
async def test_ensure_database_initialized_propagates_failure() -> None:
    """テーブル初期化例外を呼び出し元へ伝播する."""
    database = AsyncMock()
    database.initialize_tables.side_effect = RuntimeError("init failed")

    with patch(
        "grimoire_api.utils.database_init.DatabaseConnection",
        return_value=database,
    ):
        with pytest.raises(RuntimeError, match="init failed"):
            await ensure_database_initialized()


@pytest.mark.asyncio
async def test_reset_database_propagates_initialization_failure(tmp_path: Path) -> None:
    """リセット後の初期化例外も呼び出し元へ伝播する."""
    db_path = str(tmp_path / "database.db")

    with patch(
        "grimoire_api.utils.database_init.ensure_database_initialized",
        new=AsyncMock(side_effect=RuntimeError("init failed")),
    ):
        with pytest.raises(RuntimeError, match="init failed"):
            await reset_database(db_path)
