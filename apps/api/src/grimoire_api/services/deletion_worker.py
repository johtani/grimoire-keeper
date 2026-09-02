"""External cleanup executor for the page-deletion saga."""

import logging

from ..models.database import CleanupJob
from ..repositories.cleanup_job_repository import CleanupJobRepository
from ..repositories.file_repository import FileRepository
from .vectorizer import VectorizerService

logger = logging.getLogger(__name__)


class DeletionWorker:
    """cleanup job の外部削除と SQLite 確定を実行する."""

    def __init__(
        self,
        cleanup_repo: CleanupJobRepository,
        file_repo: FileRepository,
        vectorizer: VectorizerService,
    ):
        self.cleanup_repo = cleanup_repo
        self.file_repo = file_repo
        self.vectorizer = vectorizer

    async def recover_running(self) -> None:
        await self.cleanup_repo.recover_running()

    async def run_next(self) -> bool:
        """cleanup job があれば一件処理し、取得有無を返す."""
        job = await self.cleanup_repo.claim_next()
        if job is None:
            return False
        await self._execute(job)
        return True

    async def _execute(self, job: CleanupJob) -> None:
        try:
            await self.vectorizer.delete_page_from_index(job.page_id)
            await self.file_repo.delete_json_file(job.page_id)
            await self.cleanup_repo.finalize(job)
        except Exception as exc:
            logger.exception(
                "Page cleanup failed",
                extra={"cleanup_job_id": job.id, "page_id": job.page_id},
            )
            await self.cleanup_repo.retry(job.id, str(exc))
