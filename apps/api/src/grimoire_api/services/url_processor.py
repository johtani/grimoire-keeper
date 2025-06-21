"""URL processing service."""

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

    async def process_url(self, url: str, memo: str | None = None) -> dict[str, Any]:
        """URL処理のメインフロー.

        Args:
            url: 処理対象のURL
            memo: ユーザーメモ

        Returns:
            処理結果

        Raises:
            GrimoireAPIError: 処理エラー
        """
        log_id = None
        page_id = None

        try:
            # 1. 処理開始ログ
            log_id = await self.log_repo.create_log(url, "started")

            # 2. Jina AI Reader処理
            jina_result = await self.jina_client.fetch_content(url)
            page_id = await self._save_download_result(log_id, url, memo or "", jina_result)

            # 3. LLM処理
            llm_result = await self.llm_service.generate_summary_keywords(page_id)
            await self._save_llm_result(log_id, page_id, llm_result)

            # 4. ベクトル化処理
            await self.vectorizer.vectorize_content(page_id)
            await self.log_repo.update_status(log_id, "vectorize_complete")

            # 5. 完了ログ
            await self.log_repo.update_status(log_id, "completed")

            return {
                "status": "success",
                "page_id": page_id,
                "message": "URL processing completed successfully",
            }

        except Exception as e:
            if log_id:
                await self.log_repo.update_status(log_id, "failed", str(e))
            raise GrimoireAPIError(f"URL processing failed: {str(e)}")

    async def _save_download_result(
        self, log_id: int, url: str, memo: str, result: dict
    ) -> int:
        """ダウンロード結果保存.

        Args:
            log_id: ログID
            url: URL
            memo: メモ
            result: Jina AI Readerの結果

        Returns:
            作成されたページID
        """
        try:
            # pagesテーブル保存
            page_id = await self.page_repo.create_page(
                url=url, title=result["data"]["title"], memo=memo
            )

            # JSONファイル保存
            await self.page_repo.save_json_file(page_id, result)

            # ログにページID設定
            await self.log_repo.update_status(log_id, "download_complete")

            return page_id

        except Exception as e:
            await self.log_repo.update_status(log_id, "download_error", str(e))
            raise

    async def _save_llm_result(self, log_id: int, page_id: int, result: dict) -> None:
        """LLM結果保存.

        Args:
            log_id: ログID
            page_id: ページID
            result: LLMの結果
        """
        try:
            await self.page_repo.update_summary_keywords(
                page_id=page_id, summary=result["summary"], keywords=result["keywords"]
            )
            await self.log_repo.update_status(log_id, "llm_complete")

        except Exception as e:
            await self.log_repo.update_status(log_id, "llm_error", str(e))
            raise

    async def get_processing_status(self, page_id: int) -> dict[str, Any]:
        """処理状況取得.

        Args:
            page_id: ページID

        Returns:
            処理状況
        """
        try:
            # ページ情報取得
            page = await self.page_repo.get_page(page_id)
            if not page:
                return {"status": "not_found", "message": "Page not found"}

            # 最新ログ取得
            logs = await self.log_repo.get_logs_by_status("completed")
            logs.extend(await self.log_repo.get_logs_by_status("failed"))

            # 該当ページのログを検索
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
                    "has_keywords": bool(page.keywords),
                    "created_at": page.created_at.isoformat(),
                },
            }

        except Exception as e:
            return {"status": "error", "message": str(e)}
