"""Dedicated worker-process lifecycle tests."""

import asyncio
import signal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from grimoire_api.worker import run_worker, worker_lifespan
from grimoire_api.worker_lock import WorkerAlreadyRunningError


@pytest.fixture(autouse=True)
def worker_database_path(tmp_path, monkeypatch) -> None:
    """各lifespan testのlock fileを一時ディレクトリに隔離する."""
    monkeypatch.setattr(
        "grimoire_api.worker.settings.DATABASE_PATH", str(tmp_path / "grimoire.db")
    )


async def test_worker_lifespan_does_not_initialize_when_lock_is_held() -> None:
    """二重起動時はDB初期化や外部接続へ進まない."""
    lock = MagicMock()
    lock.__enter__.side_effect = WorkerAlreadyRunningError("already running")
    manager_class = MagicMock()

    with (
        patch("grimoire_api.worker.WorkerLock", return_value=lock),
        patch(
            "grimoire_api.worker.ensure_database_initialized", new=AsyncMock()
        ) as initialize,
        patch("grimoire_api.worker.WeaviateConnectionManager", manager_class),
    ):
        with pytest.raises(WorkerAlreadyRunningError, match="already running"):
            async with worker_lifespan():
                raise AssertionError("worker lifespan must not start")

    initialize.assert_not_awaited()
    manager_class.assert_not_called()


async def test_worker_lifespan_starts_and_stops_dedicated_worker() -> None:
    """Weaviate 接続中だけ専用 worker を稼働させる."""
    client = object()
    job_worker = MagicMock()
    job_worker.start = AsyncMock()
    job_worker.stop = AsyncMock(return_value=True)
    job_worker.wait = AsyncMock()
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


async def test_worker_lifespan_reports_claim_loop_failure() -> None:
    """claim loop の例外をプロセス監視側へ伝播する."""
    client = object()
    job_worker = MagicMock()
    job_worker.start = AsyncMock()
    job_worker.stop = AsyncMock(return_value=True)
    job_worker.wait = AsyncMock(side_effect=RuntimeError("claim failed"))
    manager = MagicMock()
    manager.get_client.return_value = client
    manager_callbacks: dict[str, object] = {}

    async def start_manager() -> None:
        await manager_callbacks["on_connected"](client)

    async def stop_manager() -> None:
        await manager_callbacks["on_disconnected"]()

    manager.start = AsyncMock(side_effect=start_manager)
    manager.stop = AsyncMock(side_effect=stop_manager)

    def make_manager(**kwargs: object) -> MagicMock:
        manager_callbacks.update(kwargs)
        return manager

    with (
        patch("grimoire_api.worker.ensure_database_initialized", new=AsyncMock()),
        patch(
            "grimoire_api.worker.WeaviateConnectionManager", side_effect=make_manager
        ),
        patch("grimoire_api.worker.build_job_worker", return_value=job_worker),
        patch("grimoire_api.worker.get_jina_client") as jina_client,
    ):
        jina_client.return_value.close = AsyncMock()
        async with worker_lifespan() as failure:
            try:
                await failure
            except RuntimeError as error:
                assert str(error) == "claim failed"
            else:
                raise AssertionError("claim loop failure must propagate")


async def test_worker_lifespan_reports_unexpected_clean_loop_exit() -> None:
    """停止要求のない claim loop 終了も障害として扱う."""
    client = object()
    job_worker = MagicMock()
    job_worker.start = AsyncMock()
    job_worker.stop = AsyncMock(return_value=True)
    job_worker.wait = AsyncMock()
    manager = MagicMock()
    manager.get_client.return_value = client
    manager_callbacks: dict[str, object] = {}

    async def start_manager() -> None:
        await manager_callbacks["on_connected"](client)

    async def stop_manager() -> None:
        await manager_callbacks["on_disconnected"]()

    manager.start = AsyncMock(side_effect=start_manager)
    manager.stop = AsyncMock(side_effect=stop_manager)

    def make_manager(**kwargs: object) -> MagicMock:
        manager_callbacks.update(kwargs)
        return manager

    with (
        patch("grimoire_api.worker.ensure_database_initialized", new=AsyncMock()),
        patch(
            "grimoire_api.worker.WeaviateConnectionManager", side_effect=make_manager
        ),
        patch("grimoire_api.worker.build_job_worker", return_value=job_worker),
        patch("grimoire_api.worker.get_jina_client") as jina_client,
    ):
        jina_client.return_value.close = AsyncMock()
        async with worker_lifespan() as failure:
            try:
                await failure
            except RuntimeError as error:
                assert str(error) == "Job worker claim loop stopped unexpectedly"
            else:
                raise AssertionError("unexpected claim loop exit must fail")


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
        worker_failure = loop.create_future()
        lifespan.return_value.__aenter__ = AsyncMock(return_value=worker_failure)
        lifespan.return_value.__aexit__ = AsyncMock(return_value=False)
        await run_worker()

    assert signal.SIGINT in callbacks
    assert signal.SIGTERM in callbacks
    assert remove_handler.call_count == 2


async def test_run_worker_propagates_claim_loop_failure() -> None:
    """supervisor の障害を main まで伝播して非0終了可能にする."""
    loop = asyncio.get_running_loop()
    worker_failure = loop.create_future()
    worker_failure.set_exception(RuntimeError("claim failed"))

    with (
        patch.object(loop, "add_signal_handler"),
        patch.object(loop, "remove_signal_handler", return_value=True),
        patch("grimoire_api.worker.worker_lifespan") as lifespan,
    ):
        lifespan.return_value.__aenter__ = AsyncMock(return_value=worker_failure)
        lifespan.return_value.__aexit__ = AsyncMock(return_value=False)
        try:
            await run_worker()
        except RuntimeError as error:
            assert str(error) == "claim failed"
        else:
            raise AssertionError("worker process failure must propagate")
