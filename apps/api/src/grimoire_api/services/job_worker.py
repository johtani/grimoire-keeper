"""Single persistent processing job worker."""

import asyncio
import logging

from ..models.database import PipelineStartStep
from ..repositories.job_repository import JobRepository
from ..repositories.log_repository import LogRepository
from ..repositories.page_repository import PageRepository
from .base_processor import BaseProcessorService

logger = logging.getLogger(__name__)


class JobWorker:
    """SQLite の queued ジョブを単一タスクで処理する."""

    def __init__(
        self,
        job_repo: JobRepository,
        page_repo: PageRepository,
        log_repo: LogRepository,
        processor: BaseProcessorService,
        poll_interval: float = 0.5,
    ):
        self.job_repo = job_repo
        self.page_repo = page_repo
        self.log_repo = log_repo
        self.processor = processor
        self.poll_interval = poll_interval
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """中断ジョブを復旧してポーリングを開始する."""
        await self.job_repo.recover_running()
        self._stop_event.clear()
        self._task = asyncio.create_task(self.run(), name="grimoire-job-worker")

    async def stop(self) -> None:
        """新規取得を止め、実行中ジョブの完了を待つ."""
        self._stop_event.set()
        if self._task is not None:
            await self._task
            self._task = None

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
        except Exception as e:
            logger.exception("Job %s failed", job_id)
            if log_id is not None:
                await self.log_repo.update_status(log_id, "failed", str(e))
            await self.job_repo.fail(job_id, page_id, str(e))
