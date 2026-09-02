"""Single persistent processing job worker."""

import asyncio
import logging
import time
from collections.abc import Callable

from ..models.database import Job, RepairStatus
from ..repositories.job_repository import JobRepository
from ..repositories.log_repository import LogRepository
from ..repositories.page_repository import PageRepository
from ..repositories.repair_repository import RepairRepository
from ..utils.datetime import utc_now
from ..utils.metrics import (
    url_processing_job_attempt_duration,
    url_processing_job_attempts,
    url_processing_job_completions,
    url_processing_job_duration,
    worker_job_claims,
    worker_loop_heartbeats,
)
from .base_processor import BaseProcessorService
from .deletion_worker import DeletionWorker
from .repair_service import validate_stored_source

logger = logging.getLogger(__name__)


class JobWorker:
    """SQLite の queued ジョブを単一タスクで処理する."""

    def __init__(
        self,
        job_repo: JobRepository,
        page_repo: PageRepository,
        log_repo: LogRepository,
        processor: BaseProcessorService,
        repair_repo: RepairRepository | None = None,
        poll_interval: float = 0.5,
        heartbeat: Callable[[], None] | None = None,
        deletion_worker: DeletionWorker | None = None,
    ):
        self.job_repo = job_repo
        self.page_repo = page_repo
        self.log_repo = log_repo
        self.processor = processor
        self.repair_repo = repair_repo
        self.poll_interval = poll_interval
        self.heartbeat = heartbeat
        self.deletion_worker = deletion_worker
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """中断ジョブを復旧してポーリングを開始する."""
        interrupted_jobs = await self.job_repo.recover_running()
        if self.deletion_worker is not None:
            await self.deletion_worker.recover_running()
        for job in interrupted_jobs:
            self._record_interrupted_attempt(job)
            logger.info(
                "Interrupted job recovered",
                extra={
                    "event": "worker.job.recovered",
                    "job_id": job.id,
                    "page_id": job.page_id,
                    "job_kind": job.kind.value,
                    "attempt": job.attempt,
                },
            )
        self._stop_event.clear()
        self._task = asyncio.create_task(self.run(), name="grimoire-job-worker")

    async def stop(self, timeout: float | None = None) -> bool:
        """新規取得を止め、実行中ジョブを期限付きで待つ."""
        self._stop_event.set()
        task = self._task
        if task is None:
            return True
        if timeout is None:
            await task
            self._task = None
            return True
        done, _ = await asyncio.wait({task}, timeout=timeout)
        if task not in done:
            logger.warning(
                "Job worker did not stop within %.1f seconds; cancelling", timeout
            )
            task.cancel()
            task.add_done_callback(self._consume_task_result)
            return False
        await task
        self._task = None
        return True

    async def wait_stopped(self) -> None:
        """Wait until a previously detached worker task has fully stopped."""
        task = self._task
        if task is None:
            return
        await asyncio.gather(task, return_exceptions=True)
        if self._task is task:
            self._task = None

    async def wait(self) -> None:
        """Wait for the claim loop and propagate an unexpected failure."""
        task = self._task
        if task is None:
            raise RuntimeError("Job worker has not been started")
        await task

    @staticmethod
    def _consume_task_result(task: asyncio.Task[None]) -> None:
        """Retrieve a detached task result to avoid unhandled-exception warnings."""
        try:
            task.exception()
        except asyncio.CancelledError:
            pass

    async def run(self) -> None:
        """停止要求まで queued ジョブを順番に処理する."""
        while not self._stop_event.is_set():
            # stop() と claim の境界で停止要求を受けても、新しいジョブを取得しない。
            if self._stop_event.is_set():
                break
            if self.heartbeat is not None:
                self.heartbeat()
            if self.deletion_worker is not None:
                cleanup_processed = await self.deletion_worker.run_next()
                if cleanup_processed:
                    try:
                        await asyncio.wait_for(
                            self._stop_event.wait(), timeout=self.poll_interval
                        )
                    except TimeoutError:
                        pass
                    continue
            job = await self.job_repo.claim_next()
            if job is None:
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=self.poll_interval
                    )
                except TimeoutError:
                    pass
                continue
            worker_job_claims.add(1, {"job_kind": job.kind.value})
            logger.info(
                "Job claimed",
                extra={
                    "event": "worker.job.claimed",
                    "job_id": job.id,
                    "page_id": job.page_id,
                    "job_kind": job.kind.value,
                    "attempt": job.attempt,
                    "start_step": job.start_step.value,
                },
            )
            await self._execute(job)

    async def _execute(self, job: Job) -> None:
        attempt_started = time.perf_counter()
        outcome = "failed"
        finalized = False
        try:
            page = await self.page_repo.get_page(job.page_id)
            if page is None:
                raise RuntimeError("Page not found")
            await self.processor._run_pipeline_from(
                job.page_id, page.url, job.start_step, job.id
            )
            finalized = await self.job_repo.succeed(job.id, job.page_id)
            outcome = "succeeded"
            await self._resolve_repair_if_valid(job.page_id)
        except Exception as e:
            logger.error(
                "Job attempt failed",
                extra={
                    "event": "worker.job.failed",
                    "job_id": job.id,
                    "page_id": job.page_id,
                    "job_kind": job.kind.value,
                    "attempt": job.attempt,
                    "error_type": type(e).__name__,
                },
            )
            finalized = await self.job_repo.fail(job.id, job.page_id, str(e))
        finally:
            if finalized:
                attributes = {"outcome": outcome, "job_kind": job.kind.value}
                url_processing_job_attempts.add(1, attributes)
                url_processing_job_attempt_duration.record(
                    time.perf_counter() - attempt_started, attributes
                )
                url_processing_job_completions.add(1, attributes)
                url_processing_job_duration.record(
                    max((utc_now() - job.created_at).total_seconds(), 0), attributes
                )
                logger.info(
                    "Job attempt completed",
                    extra={
                        "event": "worker.job.completed",
                        "job_id": job.id,
                        "page_id": job.page_id,
                        "job_kind": job.kind.value,
                        "attempt": job.attempt,
                        "outcome": outcome,
                        "duration_seconds": time.perf_counter() - attempt_started,
                    },
                )

    @staticmethod
    def record_loop_heartbeat() -> None:
        """Record a low-cardinality claim-loop liveness metric."""
        worker_loop_heartbeats.add(1, {"status": "running"})

    @staticmethod
    def _record_interrupted_attempt(job: Job) -> None:
        """復旧トランザクションで確定した中断 attempt を一度だけ記録する."""
        attributes = {"outcome": "interrupted", "job_kind": job.kind.value}
        url_processing_job_attempts.add(1, attributes)
        if job.started_at is not None:
            url_processing_job_attempt_duration.record(
                max((utc_now() - job.started_at).total_seconds(), 0), attributes
            )

    async def _resolve_repair_if_valid(self, page_id: int) -> None:
        """正常な保存JSONとWeaviate登録を確認して修復済みにする."""
        try:
            if self.repair_repo is None:
                return
            case = await self.repair_repo.get_by_page_id(page_id)
            if case is None or case.status != RepairStatus.PENDING:
                return
            page = await self.page_repo.get_page(page_id)
            if page is None:
                return
            source = await self.processor.file_repo.load_json_file(page_id)
            registered = await self.processor.vectorizer.is_page_registered(page_id)
            if not validate_stored_source(page_id, page.url, source) and registered:
                await self.repair_repo.resolve(page_id)
        except Exception:
            logger.exception("Repair resolution check failed for page %s", page_id)
            return
