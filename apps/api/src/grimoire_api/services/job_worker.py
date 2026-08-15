"""Single persistent processing job worker."""

import asyncio
import logging

from ..models.database import PipelineStartStep, RepairStatus
from ..repositories.job_repository import JobRepository
from ..repositories.log_repository import LogRepository
from ..repositories.page_repository import PageRepository
from ..repositories.repair_repository import RepairRepository
from .base_processor import BaseProcessorService
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
    ):
        self.job_repo = job_repo
        self.page_repo = page_repo
        self.log_repo = log_repo
        self.processor = processor
        self.repair_repo = repair_repo
        self.poll_interval = poll_interval
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """中断ジョブを復旧してポーリングを開始する."""
        await self.job_repo.recover_running()
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
            job = await self.job_repo.claim_next()
            if job is None:
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=self.poll_interval
                    )
                except TimeoutError:
                    pass
                continue
            await self._execute(job.id, job.page_id, job.start_step)

    async def _execute(
        self, job_id: int, page_id: int, start_step: PipelineStartStep
    ) -> None:
        log_id: int | None = None
        try:
            page = await self.page_repo.get_page(page_id)
            if page is None:
                raise RuntimeError("Page not found")
            log_id = await self.log_repo.create_log(page.url, "job_started", page_id)
            await self.processor._run_pipeline_from(
                page_id, log_id, page.url, start_step, job_id
            )
            await self.job_repo.succeed(job_id, page_id)
            await self._resolve_repair_if_valid(page_id)
        except Exception as e:
            logger.exception("Job %s failed", job_id)
            if log_id is not None:
                await self.log_repo.update_status(log_id, "failed", str(e))
            await self.job_repo.fail(job_id, page_id, str(e))

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
