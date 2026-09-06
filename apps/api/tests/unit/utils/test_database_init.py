"""Database initialization utility tests."""

from unittest.mock import AsyncMock, patch

import pytest
from grimoire_api.utils.database_init import ensure_database_initialized


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
