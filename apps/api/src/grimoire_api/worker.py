"""Dedicated persistent job-worker process."""

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from grimoire_shared.telemetry import setup_telemetry

from .config import settings
from .dependencies import (
    get_chunking_service,
    get_db_connection,
    get_file_repository,
    get_jina_client,
)
from .repositories.job_repository import JobRepository
from .repositories.log_repository import LogRepository
from .repositories.page_repository import PageRepository
from .repositories.repair_repository import RepairRepository
from .services.base_processor import BaseProcessorService
from .services.job_worker import JobWorker
from .services.llm_service import LLMService
from .services.vectorizer import VectorizerService
from .services.weaviate_connection import WeaviateConnectionManager
from .utils.database_init import ensure_database_initialized

logger = logging.getLogger(__name__)

if not os.getenv("PYTEST_CURRENT_TEST"):
    settings.validate_required_vars()

setup_telemetry("grimoire-worker")


def build_job_worker(weaviate_client: Any) -> JobWorker:
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
    return JobWorker(job_repo, page_repo, log_repo, processor, RepairRepository(db))


@asynccontextmanager
async def worker_lifespan() -> AsyncIterator[None]:
    """Manage the dedicated worker and its Weaviate connection."""
    await ensure_database_initialized()
    logger.info("Database initialized successfully")

    job_worker: JobWorker | None = None
    retiring_worker: JobWorker | None = None
    pending_worker_start: asyncio.Task[None] | None = None

    async def start_job_worker_now(weaviate_client: Any) -> None:
        nonlocal job_worker
        worker = build_job_worker(weaviate_client)
        await worker.start()
        job_worker = worker
        logger.info("Persistent job worker started")

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
        pending_start = pending_worker_start
        if pending_start is not None:
            pending_worker_start = None
            pending_start.cancel()
            await asyncio.gather(pending_start, return_exceptions=True)
        worker = job_worker
        if worker is None:
            return
        job_worker = None
        stopped = await worker.stop(timeout=settings.WEAVIATE_WORKER_STOP_TIMEOUT)
        if stopped:
            logger.info("Persistent job worker stopped")
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
        yield
    finally:
        await manager.stop()
        await stop_job_worker()
        await get_jina_client().close()
        logger.info("Worker process shutting down")


async def run_worker() -> None:
    """Run until the process receives a shutdown signal."""
    async with worker_lifespan():
        await asyncio.Event().wait()


def main() -> None:
    """CLI entry point for the dedicated worker process."""
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
