"""Dedicated worker-process lifecycle tests."""

import asyncio
import signal
from unittest.mock import AsyncMock, MagicMock, patch

from grimoire_api.worker import run_worker, worker_lifespan


async def test_worker_lifespan_starts_and_stops_dedicated_worker() -> None:
    """Weaviate 接続中だけ専用 worker を稼働させる."""
    client = object()
    job_worker = MagicMock()
    job_worker.start = AsyncMock()
    job_worker.stop = AsyncMock(return_value=True)
    manager = MagicMock()
    manager.get_client.return_value = client
    jina_client = MagicMock()
    jina_client.close = AsyncMock()

    async def start_manager() -> None:
        await manager_callbacks["on_connected"](client)

    async def stop_manager() -> None:
        await manager_callbacks["on_disconnected"]()

    manager.start = AsyncMock(side_effect=start_manager)
    manager.stop = AsyncMock(side_effect=stop_manager)
    manager_callbacks: dict[str, object] = {}

    def make_manager(**kwargs: object) -> MagicMock:
        manager_callbacks.update(kwargs)
        return manager

    with (
        patch(
            "grimoire_api.worker.ensure_database_initialized", new=AsyncMock()
        ) as initialize,
        patch(
            "grimoire_api.worker.WeaviateConnectionManager", side_effect=make_manager
        ),
        patch("grimoire_api.worker.build_job_worker", return_value=job_worker),
        patch("grimoire_api.worker.get_jina_client", return_value=jina_client),
    ):
        async with worker_lifespan():
            job_worker.start.assert_awaited_once()

    initialize.assert_awaited_once()
    job_worker.stop.assert_awaited_once()
    manager.stop.assert_awaited_once()
    jina_client.close.assert_awaited_once()


async def test_worker_lifespan_does_not_start_after_database_failure() -> None:
    """DB 初期化失敗時は接続や worker 起動へ進まない."""
    manager_class = MagicMock()

    with (
        patch(
            "grimoire_api.worker.ensure_database_initialized",
            new=AsyncMock(side_effect=RuntimeError("database init failed")),
        ),
        patch("grimoire_api.worker.WeaviateConnectionManager", manager_class),
    ):
        try:
            async with worker_lifespan():
                raise AssertionError("worker lifespan must not start")
        except RuntimeError as error:
            assert str(error) == "database init failed"

    manager_class.assert_not_called()


async def test_run_worker_stops_on_sigterm() -> None:
    """コンテナの SIGTERM を受けて lifespan を終了する."""
    loop = asyncio.get_running_loop()
    callbacks: dict[signal.Signals, object] = {}

    def add_handler(received_signal: signal.Signals, callback: object) -> None:
        callbacks[received_signal] = callback
        if received_signal == signal.SIGTERM:
            loop.call_soon(callback)  # type: ignore[arg-type]

    with (
        patch.object(loop, "add_signal_handler", side_effect=add_handler),
        patch.object(
            loop, "remove_signal_handler", return_value=True
        ) as remove_handler,
        patch("grimoire_api.worker.worker_lifespan") as lifespan,
    ):
        lifespan.return_value.__aenter__ = AsyncMock()
        lifespan.return_value.__aexit__ = AsyncMock(return_value=False)
        await run_worker()

    assert signal.SIGINT in callbacks
    assert signal.SIGTERM in callbacks
    assert remove_handler.call_count == 2
