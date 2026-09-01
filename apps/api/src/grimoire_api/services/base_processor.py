"""Base processor service with shared save logic."""

import logging
import time
from collections.abc import Awaitable, Callable

from ..models.database import PipelineStartStep, ProcessingStep
from ..models.external import FetchedDocument, SummaryResult
from ..repositories.file_repository import FileRepository
from ..repositories.job_repository import JobRepository
from ..repositories.log_repository import LogRepository
from ..repositories.page_repository import PageRepository
from ..utils.metrics import worker_pipeline_step_duration
from .jina_client import JinaClient
from .llm_service import LLMService
from .vectorizer import VectorizerService

logger = logging.getLogger(__name__)


class BaseProcessorService:
    """保存ロジックを共有するベースクラス."""

    def __init__(
        self,
        jina_client: JinaClient,
        llm_service: LLMService,
        vectorizer: VectorizerService,
        page_repo: PageRepository,
        log_repo: LogRepository,
        file_repo: FileRepository,
        job_repo: JobRepository | None = None,
    ):
        """初期化."""
        self.jina_client = jina_client
        self.llm_service = llm_service
        self.vectorizer = vectorizer
        self.page_repo = page_repo
        self.log_repo = log_repo
        self.file_repo = file_repo
        self.job_repo = job_repo

    async def _save_download_result(
        self, page_id: int, result: FetchedDocument
    ) -> None:
        """ダウンロード結果保存."""
        try:
            await self.file_repo.save_json_file(page_id, result.raw_response)
            await self.page_repo.update_title_and_step(
                page_id, result.title, ProcessingStep.DOWNLOADED
            )
        except Exception:
            raise

    async def _save_llm_result(self, page_id: int, result: SummaryResult) -> None:
        """LLM結果保存."""
        try:
            await self.page_repo.update_summary_keywords_and_step(
                page_id=page_id,
                summary=result.summary,
                keywords=result.keywords,
                step=ProcessingStep.LLM_PROCESSED,
            )
        except Exception:
            raise

    async def _run_pipeline_from(
        self,
        page_id: int,
        url: str,
        start_point: PipelineStartStep | str,
        job_id: int | None = None,
    ) -> None:
        """指定ポイントからパイプラインを実行する.

        Args:
            page_id: 処理対象ページID
            url: 処理対象URL
            start_point: 型制約された開始ポイント
        """
        start_step = PipelineStartStep(start_point)
        if start_step == PipelineStartStep.DOWNLOAD:

            async def download() -> None:
                jina_result = await self.jina_client.fetch_content(url)
                await self._save_download_result(page_id, jina_result)
                if self.job_repo and job_id:
                    await self.job_repo.update_step(job_id, ProcessingStep.DOWNLOADED)

            await self._run_observed_step("download", page_id, job_id, download)
        if start_step in (PipelineStartStep.DOWNLOAD, PipelineStartStep.LLM):

            async def process_llm() -> None:
                llm_result = await self.llm_service.generate_summary_keywords(page_id)
                await self._save_llm_result(page_id, llm_result)
                if self.job_repo and job_id:
                    await self.job_repo.update_step(
                        job_id, ProcessingStep.LLM_PROCESSED
                    )

            await self._run_observed_step("llm", page_id, job_id, process_llm)
        if start_step in (
            PipelineStartStep.DOWNLOAD,
            PipelineStartStep.LLM,
            PipelineStartStep.VECTORIZE,
        ):

            async def vectorize() -> None:
                try:
                    await self.vectorizer.vectorize_content(page_id)
                except Exception:
                    await self.page_repo.clear_weaviate_id(page_id)
                    raise
                await self.page_repo.update_success_step(
                    page_id, ProcessingStep.VECTORIZED
                )
                if self.job_repo and job_id:
                    await self.job_repo.update_step(job_id, ProcessingStep.VECTORIZED)

            await self._run_observed_step("vectorize", page_id, job_id, vectorize)

        async def complete() -> None:
            await self.page_repo.update_success_step(page_id, ProcessingStep.COMPLETED)
            if self.job_repo and job_id:
                await self.job_repo.update_step(job_id, ProcessingStep.COMPLETED)

        await self._run_observed_step("complete", page_id, job_id, complete)

    async def _run_observed_step(
        self,
        step: str,
        page_id: int,
        job_id: int | None,
        operation: Callable[[], Awaitable[None]],
    ) -> None:
        """Run one pipeline step with redacted structured diagnostics."""
        started = time.perf_counter()
        outcome = "failed"
        logger.info(
            "Pipeline step started",
            extra={
                "event": "worker.step.started",
                "step": step,
                "page_id": page_id,
                "job_id": job_id,
            },
        )
        try:
            await operation()
            outcome = "succeeded"
        finally:
            duration = time.perf_counter() - started
            attributes = {"step": step, "outcome": outcome}
            worker_pipeline_step_duration.record(duration, attributes)
            logger.info(
                "Pipeline step completed",
                extra={
                    "event": "worker.step.completed",
                    "step": step,
                    "page_id": page_id,
                    "job_id": job_id,
                    "outcome": outcome,
                    "duration_seconds": duration,
                },
            )
