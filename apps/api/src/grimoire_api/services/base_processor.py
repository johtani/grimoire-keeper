"""Base processor service with shared save logic."""

from ..models.database import ProcessingStep
from ..repositories.file_repository import FileRepository
from ..repositories.log_repository import LogRepository
from ..repositories.page_repository import PageRepository
from .jina_client import JinaClient
from .llm_service import LLMService
from .vectorizer import VectorizerService


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
    ):
        """初期化."""
        self.jina_client = jina_client
        self.llm_service = llm_service
        self.vectorizer = vectorizer
        self.page_repo = page_repo
        self.log_repo = log_repo
        self.file_repo = file_repo

    async def _save_download_result(
        self, log_id: int, page_id: int, result: dict
    ) -> None:
        """ダウンロード結果保存."""
        try:
            await self.file_repo.save_json_file(page_id, result)
            await self.page_repo.update_title_and_step(
                page_id, result["data"]["title"], ProcessingStep.DOWNLOADED
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
                step=ProcessingStep.LLM_PROCESSED,
            )
            await self.log_repo.update_status(log_id, "llm_complete")
        except Exception as e:
            await self.log_repo.update_status(log_id, "llm_error", str(e))
            raise

    async def _run_pipeline_from(
        self, page_id: int, log_id: int, url: str, start_point: str
    ) -> None:
        """指定ポイントからパイプラインを実行する.

        Args:
            page_id: 処理対象ページID
            log_id: ログID
            url: 処理対象URL
            start_point: 開始ポイント ("download" | "llm" | "vectorize")
        """
        if start_point == "download":
            jina_result = await self.jina_client.fetch_content(url)
            await self._save_download_result(log_id, page_id, jina_result)
            start_point = "llm"
        if start_point == "llm":
            llm_result = await self.llm_service.generate_summary_keywords(page_id)
            await self._save_llm_result(log_id, page_id, llm_result)
            start_point = "vectorize"
        if start_point == "vectorize":
            try:
                await self.vectorizer.vectorize_content(page_id)
            except Exception:
                await self.page_repo.clear_weaviate_id(page_id)
                raise
            await self.page_repo.update_success_step(page_id, ProcessingStep.VECTORIZED)
            await self.log_repo.update_status(log_id, "vectorize_complete")

        await self.page_repo.update_success_step(page_id, ProcessingStep.COMPLETED)
        await self.log_repo.update_status(log_id, "completed")
