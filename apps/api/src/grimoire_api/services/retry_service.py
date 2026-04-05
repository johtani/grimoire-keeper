"""Retry processing service."""

import logging
from typing import Any

from ..models.database import ProcessingStep
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
    ):
        """初期化."""
        super().__init__(page_repo=page_repo, log_repo=log_repo)
        self.jina_client = jina_client
        self.llm_service = llm_service
        self.vectorizer = vectorizer

    async def get_retry_start_point(self, page_id: int) -> str:
        """再処理開始ポイントを取得."""
        page = await self.page_repo.get_page(page_id)
        if not page:
            raise GrimoireAPIError(f"Page {page_id} not found")

        if not page.last_success_step:
            return "download"
        elif page.last_success_step == ProcessingStep.DOWNLOADED:
            return "llm"
        elif page.last_success_step == ProcessingStep.LLM_PROCESSED:
            return "vectorize"
        elif page.last_success_step == ProcessingStep.VECTORIZED:
            return "complete"
        else:
            return "download"

    async def retry_single_page(self, page_id: int) -> dict[str, Any]:
        """単一ページの再処理."""
        try:
            page = await self.page_repo.get_page(page_id)
            if not page:
                raise GrimoireAPIError(f"Page {page_id} not found")

            failed_logs = await self.log_repo.get_logs_by_status("failed")
            is_failed = any(log.page_id == page_id for log in failed_logs)

            if not is_failed:
                return {
                    "status": "not_failed",
                    "page_id": page_id,
                    "message": "Page is not in failed state",
                }

            start_point = await self.get_retry_start_point(page_id)

            if start_point == "complete":
                return {
                    "status": "already_completed",
                    "page_id": page_id,
                    "message": "Page is already completed",
                }

            log_id = await self.log_repo.create_log(page.url, "retry_started", page_id)
            await self._execute_retry_from_point(page_id, log_id, page.url, start_point)

            return {
                "status": "retry_started",
                "page_id": page_id,
                "restart_from": start_point,
                "message": f"Retry processing started from {start_point} step",
            }

        except Exception as e:
            raise GrimoireAPIError(f"Retry failed: {str(e)}")

    async def reprocess_page(
        self, page_id: int, from_step: str = "auto"
    ) -> dict[str, Any]:
        """ページの再処理（成功済みも対象）."""
        try:
            page = await self.page_repo.get_page(page_id)
            if not page:
                raise GrimoireAPIError(f"Page {page_id} not found")

            if from_step == "auto":
                start_point = await self.get_retry_start_point(page_id)
                if start_point == "complete":
                    start_point = "vectorize"
            else:
                start_point = from_step

            log_id = await self.log_repo.create_log(
                page.url, "reprocess_started", page_id
            )
            await self._execute_retry_from_point(page_id, log_id, page.url, start_point)

            return {
                "status": "reprocess_started",
                "page_id": page_id,
                "restart_from": start_point,
                "message": f"Reprocessing started from {start_point} step",
            }

        except Exception as e:
            raise GrimoireAPIError(f"Reprocess failed: {str(e)}")

    async def retry_all_failed(
        self, max_retries: int | None = None, delay_seconds: int = 1
    ) -> dict[str, Any]:
        """全失敗ページの再処理."""
        try:
            failed_logs = await self.log_repo.get_logs_by_status("failed")
            failed_page_ids = list(
                set(log.page_id for log in failed_logs if log.page_id)
            )

            if not failed_page_ids:
                return {
                    "status": "no_failed_pages",
                    "total_failed_pages": 0,
                    "retry_count": 0,
                    "message": "No failed pages found",
                }

            if max_retries:
                failed_page_ids = failed_page_ids[:max_retries]

            retry_count = 0
            for page_id in failed_page_ids:
                try:
                    await self.retry_single_page(page_id)
                    retry_count += 1

                    if delay_seconds > 0:
                        import asyncio

                        await asyncio.sleep(delay_seconds)

                except Exception as e:
                    # 個別の失敗は無視して続行
                    logger.error(f"Failed to retry page_id={page_id}: {e}")
                    continue

            return {
                "status": "batch_retry_started",
                "total_failed_pages": len(failed_page_ids),
                "retry_count": retry_count,
                "message": f"Batch retry started for {retry_count} failed pages",
            }

        except Exception as e:
            raise GrimoireAPIError(f"Batch retry failed: {str(e)}")

    async def _execute_retry_from_point(
        self, page_id: int, log_id: int, url: str, start_point: str
    ) -> None:
        """指定ポイントから再処理実行."""
        try:
            if start_point == "download":
                jina_result = await self.jina_client.fetch_content(url)
                await self._save_download_result(log_id, page_id, jina_result)

                llm_result = await self.llm_service.generate_summary_keywords(page_id)
                await self._save_llm_result(log_id, page_id, llm_result)

                await self.vectorizer.vectorize_content(page_id)
                await self.page_repo.update_success_step(
                    page_id, ProcessingStep.VECTORIZED
                )
                await self.log_repo.update_status(log_id, "vectorize_complete")

            elif start_point == "llm":
                llm_result = await self.llm_service.generate_summary_keywords(page_id)
                await self._save_llm_result(log_id, page_id, llm_result)

                await self.vectorizer.vectorize_content(page_id)
                await self.page_repo.update_success_step(
                    page_id, ProcessingStep.VECTORIZED
                )
                await self.log_repo.update_status(log_id, "vectorize_complete")

            elif start_point == "vectorize":
                await self.vectorizer.vectorize_content(page_id)
                await self.page_repo.update_success_step(
                    page_id, ProcessingStep.VECTORIZED
                )
                await self.log_repo.update_status(log_id, "vectorize_complete")

            # 完了処理
            await self.page_repo.update_success_step(page_id, ProcessingStep.COMPLETED)
            await self.log_repo.update_status(log_id, "completed")

        except Exception as e:
            await self.log_repo.update_status(log_id, "failed", str(e))
            raise
