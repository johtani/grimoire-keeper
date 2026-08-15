"""Tests for Weaviate connection lifecycle management."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from grimoire_api.services.weaviate_connection import WeaviateConnectionManager


@pytest.fixture(autouse=True)
def run_thread_calls_inline() -> object:
    """Avoid real worker threads while testing synchronous SDK calls."""

    async def inline(function: object, *args: object, **kwargs: object) -> object:
        return function(*args, **kwargs)  # type: ignore[operator]

    with patch(
        "grimoire_api.services.weaviate_connection.asyncio.to_thread",
        side_effect=inline,
    ) as mocked:
        yield mocked


def make_manager(**kwargs: object) -> WeaviateConnectionManager:
    """Create a manager with fast test defaults."""
    return WeaviateConnectionManager(
        host="weaviate",
        port=8080,
        api_key="test-key",
        startup_attempts=1,
        startup_interval=0,
        monitor_interval=3600,
        **kwargs,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_start_connects_and_stop_closes_client() -> None:
    client = MagicMock()
    client.is_ready.return_value = True
    on_connected = AsyncMock()
    on_disconnected = AsyncMock()
    manager = make_manager(on_connected=on_connected, on_disconnected=on_disconnected)

    with patch(
        "grimoire_api.services.weaviate_connection.weaviate.connect_to_local",
        return_value=client,
    ) as connect:
        await asyncio.wait_for(manager.start(), timeout=1)
        assert manager.get_client() is client
        assert manager.is_available
        connect.assert_called_once()
        on_connected.assert_awaited_once_with(client)

        await asyncio.wait_for(manager.stop(), timeout=1)

    assert not manager.is_available
    on_disconnected.assert_awaited_once()
    client.close.assert_called_once()


@pytest.mark.asyncio
async def test_start_retries_until_connection_succeeds() -> None:
    client = MagicMock()
    client.is_ready.return_value = True
    manager = WeaviateConnectionManager(
        "weaviate", 8080, "test-key", startup_attempts=3, startup_interval=0
    )

    with patch(
        "grimoire_api.services.weaviate_connection.weaviate.connect_to_local",
        side_effect=[RuntimeError("not ready"), client],
    ) as connect:
        await manager.start()
        await manager.stop()

    assert connect.call_count == 2


@pytest.mark.asyncio
async def test_start_continues_degraded_after_retry_limit() -> None:
    manager = make_manager()

    with patch(
        "grimoire_api.services.weaviate_connection.weaviate.connect_to_local",
        side_effect=RuntimeError("offline"),
    ):
        await manager.start()
        assert manager.get_client() is None
        assert manager._monitor_task is not None
        await manager.stop()


@pytest.mark.asyncio
async def test_monitor_reconnects_after_initial_failure() -> None:
    client = MagicMock()
    client.is_ready.return_value = True
    connected = asyncio.Event()

    async def on_connected(_: object) -> None:
        connected.set()

    manager = WeaviateConnectionManager(
        "weaviate",
        8080,
        "test-key",
        startup_attempts=1,
        startup_interval=0,
        monitor_interval=0.01,
        on_connected=on_connected,  # type: ignore[arg-type]
    )

    with patch(
        "grimoire_api.services.weaviate_connection.weaviate.connect_to_local",
        side_effect=[RuntimeError("offline"), client],
    ):
        await manager.start()
        await asyncio.wait_for(connected.wait(), timeout=1)
        assert manager.get_client() is client
        await manager.stop()


@pytest.mark.asyncio
async def test_monitor_replaces_client_after_connection_loss() -> None:
    old_client = MagicMock()
    old_client.is_ready.side_effect = [True, False]
    new_client = MagicMock()
    new_client.is_ready.return_value = True
    on_connected = AsyncMock()
    on_disconnected = AsyncMock()
    manager = WeaviateConnectionManager(
        "weaviate",
        8080,
        "test-key",
        startup_attempts=1,
        monitor_interval=0.01,
        on_connected=on_connected,
        on_disconnected=on_disconnected,
    )

    with patch(
        "grimoire_api.services.weaviate_connection.weaviate.connect_to_local",
        side_effect=[old_client, new_client],
    ):
        await manager.start()
        for _ in range(100):
            if manager.get_client() is new_client:
                break
            await asyncio.sleep(0.01)
        assert manager.get_client() is new_client
        assert on_connected.await_count == 2
        assert on_disconnected.await_count == 1
        await manager.stop()

    assert old_client.close.call_count == 1
    assert on_disconnected.await_count == 2
