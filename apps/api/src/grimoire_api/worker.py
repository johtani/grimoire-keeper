"""Dedicated persistent job-worker process."""

import asyncio
import logging
import os
import signal
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from grimoire_shared.telemetry import redact_http_url, setup_telemetry
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlite3 import SQLite3Instrumentor

from .config import settings
from .dependencies import (
    get_chunking_service,
    get_db_connection,
    get_file_repository,
    get_jina_client,
)
from .repositories.cleanup_job_repository import CleanupJobRepository
from .repositories.job_repository import JobRepository
from .repositories.log_repository import LogRepository
from .repositories.page_repository import PageRepository
from .repositories.repair_repository import RepairRepository
from .services.base_processor import BaseProcessorService
from .services.deletion_worker import DeletionWorker
from .services.job_worker import JobWorker
from .services.llm_service import LLMService
from .services.vectorizer import VectorizerService
from .services.weaviate_connection import WeaviateConnectionManager
from .utils.database_init import ensure_database_initialized
from .worker_health import WorkerHealth
from .worker_lock import WorkerLock

logger = logging.getLogger(__name__)

if not os.getenv("PYTEST_CURRENT_TEST"):
    settings.validate_worker_required_vars()

telemetry_is_enabled = setup_telemetry("grimoire-worker")
if telemetry_is_enabled:
    HTTPXClientInstrumentor().instrument(request_hook=redact_http_url)
    SQLite3Instrumentor().instrument()


def build_job_worker(
    weaviate_client: Any, heartbeat: Callable[[], None] | None = None
) -> JobWorker:
    """Build a job worker with process-local dependencies."""
    db = get_db_connection()
    page_repo = PageRepository(db)
    log_repo = LogRepository(db)
    job_repo = JobRepository(db)
    file_repo = get_file_repository()
    processor = BaseProcessorService(
        jina_client=get_jina_client(),
        llm_service=LLMService(file_repo),
        vectorizer=VectorizerService(
            page_repo,
            file_repo,
            get_chunking_service(),
            weaviate_client,
        ),
        page_repo=page_repo,
        log_repo=log_repo,
        file_repo=file_repo,
        job_repo=job_repo,
    )
    vectorizer = processor.vectorizer
    deletion_worker = DeletionWorker(CleanupJobRepository(db), file_repo, vectorizer)
    return JobWorker(
        job_repo,
        page_repo,
        log_repo,
        processor,
        RepairRepository(db),
        heartbeat=heartbeat,
        deletion_worker=deletion_worker,
    )


@asynccontextmanager
async def worker_lifespan() -> AsyncIterator[asyncio.Future[None]]:
    """Manage the dedicated worker and its Weaviate connection."""
    with WorkerLock(settings.DATABASE_PATH):
        async with _locked_worker_lifespan() as failure:
            yield failure


@asynccontextmanager
async def _locked_worker_lifespan() -> AsyncIterator[asyncio.Future[None]]:
    """Manage worker resources after obtaining the process-level lock."""
    health = WorkerHealth()
    health.heartbeat()
    logger.info("Worker process starting", extra={"event": "worker.starting"})
    await ensure_database_initialized()
    logger.info("Database initialized successfully")

    job_worker: JobWorker | None = None
    retiring_worker: JobWorker | None = None
    pending_worker_start: asyncio.Task[None] | None = None
    monitor_task: asyncio.Task[None] | None = None
    health_task: asyncio.Task[None] | None = None
    failure = asyncio.get_running_loop().create_future()

    async def monitor_job_worker(worker: JobWorker) -> None:
        try:
            await worker.wait()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if job_worker is worker and not failure.done():
                failure.set_exception(error)
        else:
            if job_worker is worker and not failure.done():
                failure.set_exception(
                    RuntimeError("Job worker claim loop stopped unexpectedly")
                )

    async def publish_health(worker: JobWorker) -> None:
        heartbeat_count = 0
        while job_worker is worker:
            health.heartbeat()
            worker.record_loop_heartbeat()
            heartbeat_count += 1
            if heartbeat_count == 1 or heartbeat_count % 12 == 0:
                logger.info(
                    "Worker claim loop heartbeat",
                    extra={"event": "worker.heartbeat", "status": "running"},
                )
            await asyncio.sleep(5)

    async def start_job_worker_now(weaviate_client: Any) -> None:
        nonlocal job_worker, monitor_task, health_task
        worker = build_job_worker(weaviate_client, health.record_claim)
        await worker.start()
        job_worker = worker
        health.mark_running()
        monitor_task = asyncio.create_task(
            monitor_job_worker(worker), name="grimoire-job-worker-supervisor"
        )
        health_task = asyncio.create_task(
            publish_health(worker), name="grimoire-job-worker-health"
        )
        logger.info(
            "Persistent job worker started",
            extra={"event": "worker.started", "status": "running"},
        )

    async def start_job_worker(weaviate_client: Any) -> None:
        nonlocal pending_worker_start, retiring_worker
        if job_worker is not None or pending_worker_start is not None:
            return
        if retiring_worker is None:
            await start_job_worker_now(weaviate_client)
            return

        worker_to_wait = retiring_worker

        async def start_after_retirement() -> None:
            nonlocal pending_worker_start, retiring_worker
            try:
                await asyncio.shield(worker_to_wait.wait_stopped())
                if retiring_worker is worker_to_wait:
                    retiring_worker = None
                while manager.get_client() is weaviate_client and job_worker is None:
                    try:
                        await start_job_worker_now(weaviate_client)
                    except Exception:
                        logger.exception(
                            "Persistent job worker restart failed; retrying"
                        )
                        await asyncio.sleep(settings.WEAVIATE_MONITOR_INTERVAL)
            finally:
                pending_worker_start = None

        pending_worker_start = asyncio.create_task(
            start_after_retirement(), name="grimoire-job-worker-restart"
        )

    async def stop_job_worker() -> None:
        nonlocal job_worker, pending_worker_start, retiring_worker
        nonlocal monitor_task, health_task
        pending_start = pending_worker_start
        if pending_start is not None:
            pending_worker_start = None
            pending_start.cancel()
            await asyncio.gather(pending_start, return_exceptions=True)
        worker = job_worker
        if worker is None:
            return
        job_worker = None
        health.mark_stopped()
        current_health_task = health_task
        health_task = None
        if current_health_task is not None:
            current_health_task.cancel()
            await asyncio.gather(current_health_task, return_exceptions=True)
        stopped = await worker.stop(timeout=settings.WEAVIATE_WORKER_STOP_TIMEOUT)
        current_monitor = monitor_task
        monitor_task = None
        if stopped and current_monitor is not None:
            await asyncio.gather(current_monitor, return_exceptions=True)
        if stopped:
            logger.info(
                "Persistent job worker stopped",
                extra={"event": "worker.stopped", "status": "stopped"},
            )
        else:
            retiring_worker = worker
            logger.warning("Persistent job worker is still retiring")

    manager = WeaviateConnectionManager(
        host=settings.WEAVIATE_HOST,
        port=settings.WEAVIATE_PORT,
        api_key=settings.OPENAI_API_KEY,
        startup_attempts=settings.WEAVIATE_STARTUP_RETRY_ATTEMPTS,
        startup_interval=settings.WEAVIATE_STARTUP_RETRY_INTERVAL,
        startup_timeout=settings.WEAVIATE_STARTUP_TIMEOUT,
        connect_timeout=settings.WEAVIATE_CONNECT_TIMEOUT,
        monitor_interval=settings.WEAVIATE_MONITOR_INTERVAL,
        on_connected=start_job_worker,
        on_disconnected=stop_job_worker,
    )
    try:
        await manager.start()
        yield failure
    finally:
        try:
            await manager.stop()
            await stop_job_worker()
        finally:
            await get_jina_client().close()
            logger.info(
                "Worker process shutting down",
                extra={"event": "worker.shutdown"},
            )


async def run_worker() -> None:
    """Run until the process receives a shutdown signal."""
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()
    handled_signals = (signal.SIGINT, signal.SIGTERM)
    for handled_signal in handled_signals:
        loop.add_signal_handler(handled_signal, shutdown_event.set)
    try:
        async with worker_lifespan() as worker_failure:
            shutdown_waiter = asyncio.create_task(shutdown_event.wait())
            waiters: set[asyncio.Future[Any]] = {shutdown_waiter, worker_failure}
            done, _ = await asyncio.wait(
                waiters,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if worker_failure in done:
                shutdown_waiter.cancel()
                await asyncio.gather(shutdown_waiter, return_exceptions=True)
                await worker_failure
    finally:
        for handled_signal in handled_signals:
            loop.remove_signal_handler(handled_signal)


def main() -> None:
    """CLI entry point for the dedicated worker process."""
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
