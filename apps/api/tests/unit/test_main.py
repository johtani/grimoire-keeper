"""Application lifespan tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from grimoire_api.main import app, lifespan


@pytest.mark.asyncio
async def test_lifespan_starts_and_stops_manager_after_database_init() -> None:
    """DB 初期化成功後に Weaviate manager を起動・停止する."""
    manager = MagicMock()
    manager.start = AsyncMock()
    manager.stop = AsyncMock()
    jina_client = MagicMock()
    jina_client.close = AsyncMock()

    with (
        patch(
            "grimoire_api.main.ensure_database_initialized", new=AsyncMock()
        ) as initialize,
        patch("grimoire_api.main.WeaviateConnectionManager", return_value=manager),
        patch("grimoire_api.main.get_jina_client", return_value=jina_client),
    ):
        async with lifespan(app):
            manager.start.assert_awaited_once()

    initialize.assert_awaited_once()
    manager.stop.assert_awaited_once()
    jina_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifespan_does_not_start_manager_when_database_init_fails() -> None:
    """DB 初期化失敗時は Weaviate manager や worker の起動に進まない."""
    manager_class = MagicMock()

    with (
        patch(
            "grimoire_api.main.ensure_database_initialized",
            new=AsyncMock(side_effect=RuntimeError("database init failed")),
        ),
        patch("grimoire_api.main.WeaviateConnectionManager", manager_class),
    ):
        with pytest.raises(RuntimeError, match="database init failed"):
            async with lifespan(app):
                pytest.fail("lifespan must not start")

    manager_class.assert_not_called()
