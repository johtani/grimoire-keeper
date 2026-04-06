"""URL processing service."""

from typing import Any

from ..models.database import ProcessingStep
from ..repositories.file_repository import FileRepository
from ..repositories.log_repository import LogRepository
from ..repositories.page_repository import PageRepository
from ..utils.exceptions import GrimoireAPIError
from .base_processor import BaseProcessorService
from .jina_client import JinaClient
from .llm_service import LLMService
from .vectorizer import VectorizerService


class UrlProcessorService(BaseProcessorService):
    """URL処理サービス."""

    def __init__(
        self,
        jina_client: JinaClient,
        llm_service: LLMService,
        vectorizer: VectorizerService,
        page_repo: PageRepository,
        log_repo: LogRepository,
        file_repo: FileRepository,
    ):
        """初期化."""
        super().__init__(page_repo=page_repo, log_repo=log_repo, file_repo=file_repo)
        self.jina_client = jina_client
        self.llm_service = llm_service
        self.vectorizer = vectorizer

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
            existing_page_id = await self.page_repo.get_page_by_url(url)
            if existing_page_id:
                return {
                    "status": "already_exists",
                    "page_id": existing_page_id,
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
            # UNIQUE制約違反は並行リクエストによる競合 — already_existsとして返す
            if "UNIQUE constraint failed" in str(e):
                existing_page_id = await self.page_repo.get_page_by_url(url)
                if existing_page_id:
                    return {
                        "status": "already_exists",
                        "page_id": existing_page_id,
                        "message": "URL already exists in the database",
                    }
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
            try:
                await self.vectorizer.vectorize_content(page_id)
            except Exception as e:
                # Weaviate書き込み失敗時はDBのweaviate_idをクリアして整合性を保つ
                await self.page_repo.clear_weaviate_id(page_id)
                raise e
            await self.log_repo.update_status(log_id, "vectorize_complete")

            # 6. 完了ログ
            await self.page_repo.update_success_step(page_id, ProcessingStep.COMPLETED)
            await self.log_repo.update_status(log_id, "completed")

        except Exception as e:
            await self.log_repo.update_status(log_id, "failed", str(e))

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
                    "keywords": page.keywords,
                    "created_at": (
                        page.created_at.replace(tzinfo=None).isoformat()
                        if page.created_at.tzinfo is None
                        else page.created_at.isoformat()
                    ),
                },
            }

        except Exception as e:
            return {"status": "error", "message": str(e)}
