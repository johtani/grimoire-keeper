"""Retry processing service."""

import logging
from typing import Any

from ..models.database import (
    JobKind,
    PageStatus,
    PipelineStartStep,
    ProcessingStep,
    ReprocessStartStep,
)
from ..repositories.file_repository import FileRepository
from ..repositories.job_repository import JobRepository
from ..repositories.log_repository import LogRepository
from ..repositories.page_repository import PageRepository
from ..utils.exceptions import GrimoireAPIError
from .base_processor import BaseProcessorService
from .jina_client import JinaClient
from .llm_service import LLMService
from .vectorizer import VectorizerService

logger = logging.getLogger(__name__)


class RetryService(BaseProcessorService):
    """再処理サービス."""

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
        super().__init__(
            jina_client=jina_client,
            llm_service=llm_service,
            vectorizer=vectorizer,
            page_repo=page_repo,
            log_repo=log_repo,
            file_repo=file_repo,
            job_repo=job_repo,
        )

    async def get_retry_start_point(self, page_id: int) -> PipelineStartStep:
        """再処理開始ポイントを取得."""
        page = await self.page_repo.get_page(page_id)
        if not page:
            raise GrimoireAPIError(f"Page {page_id} not found")

        if not page.last_success_step:
            return PipelineStartStep.DOWNLOAD
        elif page.last_success_step == ProcessingStep.DOWNLOADED:
            return PipelineStartStep.LLM
        elif page.last_success_step == ProcessingStep.LLM_PROCESSED:
            return PipelineStartStep.VECTORIZE
        elif page.last_success_step == ProcessingStep.VECTORIZED:
            return PipelineStartStep.VECTORIZE
        else:
            return PipelineStartStep.DOWNLOAD

    async def retry_single_page(self, page_id: int) -> dict[str, Any]:
        """単一ページの再処理."""
        try:
            page = await self.page_repo.get_page(page_id)
            if not page:
                raise GrimoireAPIError(f"Page {page_id} not found")

            if page.status != PageStatus.FAILED:
                return {
                    "status": "not_failed",
                    "page_id": page_id,
                    "message": "Page is not in failed state",
                }

            start_point = await self.get_retry_start_point(page_id)

            if self.job_repo is None:
                raise GrimoireAPIError("Job repository is not configured")
            job_id = await self.job_repo.enqueue(page_id, JobKind.RETRY, start_point)

            return {
                "status": "retry_started",
                "page_id": page_id,
                "job_id": job_id,
                "restart_from": start_point.value,
                "message": f"Retry processing started from {start_point} step",
            }

        except Exception as e:
            raise GrimoireAPIError(f"Retry failed: {str(e)}")

    async def reprocess_page(
        self,
        page_id: int,
        from_step: ReprocessStartStep | str = ReprocessStartStep.AUTO,
    ) -> dict[str, Any]:
        """ページの再処理（成功済みも対象）."""
        try:
            page = await self.page_repo.get_page(page_id)
            if not page:
                raise GrimoireAPIError(f"Page {page_id} not found")

            requested_step = ReprocessStartStep(from_step)
            if requested_step == ReprocessStartStep.AUTO:
                start_point = await self.get_retry_start_point(page_id)
            else:
                start_point = PipelineStartStep(requested_step.value)
            if self.job_repo is None:
                raise GrimoireAPIError("Job repository is not configured")
            job_id = await self.job_repo.enqueue(
                page_id, JobKind.REPROCESS, start_point
            )

            return {
                "status": "reprocess_started",
                "page_id": page_id,
                "job_id": job_id,
                "restart_from": start_point.value,
                "message": f"Reprocessing started from {start_point} step",
            }

        except Exception as e:
            raise GrimoireAPIError(f"Reprocess failed: {str(e)}")

    async def retry_all_failed(
        self, max_retries: int | None = None, delay_seconds: int = 1
    ) -> dict[str, Any]:
        """全失敗ページの再処理."""
        try:
            failed_pages = await self.page_repo.get_pages(
                limit=max_retries or 10000, status_filter="failed"
            )
            if not failed_pages:
                return {
                    "status": "no_failed_pages",
                    "total_failed_pages": 0,
                    "retry_count": 0,
                    "message": "No failed pages found",
                }

            retry_count = 0
            job_ids: list[int] = []
            for page in failed_pages:
                try:
                    if page.id is None:
                        continue
                    result = await self.retry_single_page(page.id)
                    job_ids.append(result["job_id"])
                    retry_count += 1

                except Exception as e:
                    # 個別の失敗は無視して続行
                    logger.error("Failed to retry page_id=%s: %s", page.id, e)
                    continue

            return {
                "status": "batch_retry_started",
                "total_failed_pages": len(failed_pages),
                "retry_count": retry_count,
                "job_ids": job_ids,
                "message": f"Batch retry started for {retry_count} failed pages",
            }

        except Exception as e:
            raise GrimoireAPIError(f"Batch retry failed: {str(e)}")

    async def _execute_retry_from_point(
        self,
        page_id: int,
        log_id: int,
        url: str,
        start_point: PipelineStartStep,
    ) -> None:
        """指定ポイントから再処理実行."""
        try:
            await self._run_pipeline_from(
                page_id=page_id, log_id=log_id, url=url, start_point=start_point
            )
        except Exception as e:
            await self.log_repo.update_status(log_id, "failed", str(e))
            raise
