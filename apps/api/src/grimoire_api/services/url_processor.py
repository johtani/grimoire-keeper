"""URL processing service."""

import json
from typing import Any

from ..repositories.log_repository import LogRepository
from ..repositories.page_repository import PageRepository
from ..utils.exceptions import GrimoireAPIError
from .jina_client import JinaClient
from .llm_service import LLMService
from .vectorizer import VectorizerService


class UrlProcessorService:
    """URL処理サービス."""

    def __init__(
        self,
        jina_client: JinaClient,
        llm_service: LLMService,
        vectorizer: VectorizerService,
        page_repo: PageRepository,
        log_repo: LogRepository,
    ):
        """初期化."""
        self.jina_client = jina_client
        self.llm_service = llm_service
        self.vectorizer = vectorizer
        self.page_repo = page_repo
        self.log_repo = log_repo

    async def prepare_url_processing(
        self, url: str, memo: str | None = None
    ) -> dict[str, Any]:
        """URL処理準備.

        Args:
            url: 処理対象のURL
            memo: ユーザーメモ

        Returns:
            準備結果
        """
        try:
            # 0. URL重複チェック
            existing_page = await self.page_repo.get_page_by_url(url)
            if existing_page:
                return {
                    "status": "already_exists",
                    "page_id": existing_page.id,
                    "message": "URL already exists in the database",
                }

            # 1. 仮のページ作成
            page_id = await self.page_repo.create_page(
                url=url, title="Processing...", memo=memo or ""
            )

            # 2. 処理開始ログ作成
            log_id = await self.log_repo.create_log(url, "started", page_id)

            return {
                "status": "prepared",
                "page_id": page_id,
                "log_id": log_id,
                "message": "Processing prepared",
            }

        except Exception as e:
            raise GrimoireAPIError(f"URL processing preparation failed: {str(e)}")

    async def process_url_background(self, page_id: int, log_id: int, url: str) -> None:
        """バックグラウンド処理."""
        try:
            # 3. Jina AI Reader処理
            jina_result = await self.jina_client.fetch_content(url)
            await self._save_download_result(log_id, page_id, jina_result)

            # 4. LLM処理
            llm_result = await self.llm_service.generate_summary_keywords(page_id)
            await self._save_llm_result(log_id, page_id, llm_result)

            # 5. ベクトル化処理
            await self.vectorizer.vectorize_content(page_id)
            await self.page_repo.update_success_step(page_id, "vectorized")
            await self.log_repo.update_status(log_id, "vectorize_complete")

            # 6. 完了ログ
            await self.page_repo.update_success_step(page_id, "completed")
            await self.log_repo.update_status(log_id, "completed")

        except Exception as e:
            await self.log_repo.update_status(log_id, "failed", str(e))

    async def process_url(self, url: str, memo: str | None = None) -> dict[str, Any]:
        """URL処理のメインフロー（後方互換性のため残存）."""
        result = await self.prepare_url_processing(url, memo)

        if result["status"] == "already_exists":
            return result

        await self.process_url_background(result["page_id"], result["log_id"], url)

        return {
            "status": "success",
            "page_id": result["page_id"],
            "message": "URL processing completed successfully",
        }

    async def _save_download_result(
        self, log_id: int, page_id: int, result: dict
    ) -> None:
        """ダウンロード結果保存."""
        try:
            await self.page_repo.update_page_title(page_id, result["data"]["title"])
            await self.page_repo.save_json_file(page_id, result)
            await self.page_repo.update_success_step(page_id, "downloaded")
            await self.log_repo.update_status(log_id, "download_complete")
        except Exception as e:
            await self.log_repo.update_status(log_id, "download_error", str(e))
            raise

    async def _save_llm_result(self, log_id: int, page_id: int, result: dict) -> None:
        """LLM結果保存."""
        try:
            await self.page_repo.update_summary_keywords(
                page_id=page_id, summary=result["summary"], keywords=result["keywords"]
            )
            await self.page_repo.update_success_step(page_id, "llm_processed")
            await self.log_repo.update_status(log_id, "llm_complete")
        except Exception as e:
            await self.log_repo.update_status(log_id, "llm_error", str(e))
            raise

    async def get_processing_status(self, page_id: int) -> dict[str, Any]:
        """処理状況取得."""
        try:
            page = await self.page_repo.get_page(page_id)
            if not page:
                return {"status": "not_found", "message": "Page not found"}

            logs = await self.log_repo.get_logs_by_status("completed")
            logs.extend(await self.log_repo.get_logs_by_status("failed"))

            page_log = None
            for log in logs:
                if log.page_id == page_id:
                    page_log = log
                    break

            if not page_log:
                return {"status": "processing", "message": "Processing in progress"}

            return {
                "status": page_log.status,
                "message": page_log.error_message or "Processing completed",
                "page": {
                    "id": page.id,
                    "url": page.url,
                    "title": page.title,
                    "memo": page.memo,
                    "summary": page.summary,
                    "keywords": json.loads(page.keywords) if page.keywords else [],
                    "created_at": (
                        page.created_at.replace(tzinfo=None).isoformat()
                        if page.created_at.tzinfo is None
                        else page.created_at.isoformat()
                    ),
                },
            }

        except Exception as e:
            return {"status": "error", "message": str(e)}
