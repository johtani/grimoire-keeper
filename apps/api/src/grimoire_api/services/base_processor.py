"""Base processor service with shared save logic."""

from ..repositories.log_repository import LogRepository
from ..repositories.page_repository import PageRepository


class BaseProcessorService:
    """保存ロジックを共有するベースクラス."""

    def __init__(self, page_repo: PageRepository, log_repo: LogRepository):
        """初期化."""
        self.page_repo = page_repo
        self.log_repo = log_repo

    async def _save_download_result(
        self, log_id: int, page_id: int, result: dict
    ) -> None:
        """ダウンロード結果保存."""
        try:
            await self.page_repo.save_json_file(page_id, result)
            await self.page_repo.update_title_and_step(
                page_id, result["data"]["title"], "downloaded"
            )
            await self.log_repo.update_status(log_id, "download_complete")
        except Exception as e:
            await self.log_repo.update_status(log_id, "download_error", str(e))
            raise

    async def _save_llm_result(self, log_id: int, page_id: int, result: dict) -> None:
        """LLM結果保存."""
        try:
            await self.page_repo.update_summary_keywords_and_step(
                page_id=page_id,
                summary=result["summary"],
                keywords=result["keywords"],
                step="llm_processed",
            )
            await self.log_repo.update_status(log_id, "llm_complete")
        except Exception as e:
            await self.log_repo.update_status(log_id, "llm_error", str(e))
            raise
