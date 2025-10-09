"""Retry processing service."""

from typing import Any

from ..repositories.log_repository import LogRepository
from ..repositories.page_repository import PageRepository
from ..utils.exceptions import GrimoireAPIError
from .jina_client import JinaClient
from .llm_service import LLMService
from .vectorizer import VectorizerService


class RetryService:
    """再処理サービス."""

    def __init__(
        self,
        jina_client: JinaClient,
        llm_service: LLMService,
        vectorizer: VectorizerService,
        page_repo: PageRepository,
        log_repo: LogRepository,
    ):
        """初期化.

        Args:
            jina_client: Jina AI Reader クライアント
            llm_service: LLMサービス
            vectorizer: ベクトル化サービス
            page_repo: ページリポジトリ
            log_repo: ログリポジトリ
        """
        self.jina_client = jina_client
        self.llm_service = llm_service
        self.vectorizer = vectorizer
        self.page_repo = page_repo
        self.log_repo = log_repo

    def get_retry_start_point(self, page_id: int) -> str:
        """再処理開始ポイントを取得.

        Args:
            page_id: ページID

        Returns:
            再処理開始ポイント
        """
        page = self.page_repo.get_page(page_id)
        if not page:
            raise GrimoireAPIError(f"Page {page_id} not found")

        if not page.last_success_step:
            return "download"
        elif page.last_success_step == "downloaded":
            return "llm"
        elif page.last_success_step == "llm_processed":
            return "vectorize"
        elif page.last_success_step == "vectorized":
            return "complete"
        else:
            return "download"

    async def retry_single_page(self, page_id: int) -> dict[str, Any]:
        """単一ページの再処理.

        Args:
            page_id: ページID

        Returns:
            再処理結果
        """
        try:
            page = self.page_repo.get_page(page_id)
            if not page:
                raise GrimoireAPIError(f"Page {page_id} not found")

            # 失敗状態かチェック
            failed_logs = self.log_repo.get_logs_by_status("failed")
            is_failed = any(log.page_id == page_id for log in failed_logs)

            if not is_failed:
                return {
                    "status": "not_failed",
                    "page_id": page_id,
                    "message": "Page is not in failed state",
                }

            # 再処理開始ポイントを決定
            start_point = self.get_retry_start_point(page_id)

            if start_point == "complete":
                return {
                    "status": "already_completed",
                    "page_id": page_id,
                    "message": "Page is already completed",
                }

            # 新しいログ作成
            log_id = self.log_repo.create_log(page.url, "retry_started", page_id)

            # 再処理実行
            await self._execute_retry_from_point(page_id, log_id, page.url, start_point)

            return {
                "status": "retry_started",
                "page_id": page_id,
                "restart_from": start_point,
                "message": f"Retry processing started from {start_point} step",
            }

        except Exception as e:
            raise GrimoireAPIError(f"Retry failed: {str(e)}")

    async def retry_all_failed(
        self, max_retries: int | None = None, delay_seconds: int = 1
    ) -> dict[str, Any]:
        """全失敗ページの再処理.

        Args:
            max_retries: 最大再処理数
            delay_seconds: 遅延秒数

        Returns:
            再処理結果
        """
        try:
            # 失敗ページを取得
            failed_logs = self.log_repo.get_logs_by_status("failed")
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

            # 再処理数を制限
            if max_retries:
                failed_page_ids = failed_page_ids[:max_retries]

            retry_count = 0
            for page_id in failed_page_ids:
                try:
                    await self.retry_single_page(page_id)
                    retry_count += 1

                    # 遅延
                    if delay_seconds > 0:
                        import asyncio
                        await asyncio.sleep(delay_seconds)

                except Exception:
                    # 個別の失敗は無視して続行
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
        """指定ポイントから再処理実行.

        Args:
            page_id: ページID
            log_id: ログID
            url: URL
            start_point: 開始ポイント
        """
        try:
            if start_point == "download":
                # コンテンツ取得から開始
                jina_result = await self.jina_client.fetch_content(url)
                await self._save_download_result(log_id, page_id, jina_result)

                # LLM処理
                llm_result = await self.llm_service.generate_summary_keywords(page_id)
                await self._save_llm_result(log_id, page_id, llm_result)

                # ベクトル化
                await self.vectorizer.vectorize_content(page_id)
                self.page_repo.update_success_step(page_id, "vectorized")
                self.log_repo.update_status(log_id, "vectorize_complete")

            elif start_point == "llm":
                # LLM処理から開始
                llm_result = await self.llm_service.generate_summary_keywords(page_id)
                await self._save_llm_result(log_id, page_id, llm_result)

                # ベクトル化
                await self.vectorizer.vectorize_content(page_id)
                self.page_repo.update_success_step(page_id, "vectorized")
                self.log_repo.update_status(log_id, "vectorize_complete")

            elif start_point == "vectorize":
                # ベクトル化から開始
                await self.vectorizer.vectorize_content(page_id)
                self.page_repo.update_success_step(page_id, "vectorized")
                self.log_repo.update_status(log_id, "vectorize_complete")

            # 完了処理
            self.page_repo.update_success_step(page_id, "completed")
            self.log_repo.update_status(log_id, "completed")

        except Exception as e:
            self.log_repo.update_status(log_id, "failed", str(e))
            raise

    async def _save_download_result(
        self, log_id: int, page_id: int, result: dict
    ) -> None:
        """ダウンロード結果保存.

        Args:
            log_id: ログID
            page_id: ページID
            result: Jina AI Readerの結果
        """
        try:
            self.page_repo.update_page_title(page_id, result["data"]["title"])
            self.page_repo.save_json_file(page_id, result)
            self.page_repo.update_success_step(page_id, "downloaded")
            self.log_repo.update_status(log_id, "download_complete")
        except Exception as e:
            self.log_repo.update_status(log_id, "download_error", str(e))
            raise

    async def _save_llm_result(self, log_id: int, page_id: int, result: dict) -> None:
        """LLM結果保存.

        Args:
            log_id: ログID
            page_id: ページID
            result: LLMの結果
        """
        try:
            self.page_repo.update_summary_keywords(
                page_id=page_id, summary=result["summary"], keywords=result["keywords"]
            )
            self.page_repo.update_success_step(page_id, "llm_processed")
            self.log_repo.update_status(log_id, "llm_complete")
        except Exception as e:
            self.log_repo.update_status(log_id, "llm_error", str(e))
            raise
