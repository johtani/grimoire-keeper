"""Page deletion request service."""

from typing import Any

from ..repositories.cleanup_job_repository import CleanupJobRepository
from ..repositories.page_repository import PageRepository


class PageDeletionService:
    """Validate a page and enqueue its durable cleanup job."""

    def __init__(
        self,
        page_repo: PageRepository,
        cleanup_repo: CleanupJobRepository,
    ) -> None:
        self.page_repo = page_repo
        self.cleanup_repo = cleanup_repo

    async def delete_page(self, page_id: int) -> dict[str, Any]:
        """Accept an asynchronous, idempotent page deletion request."""
        page = await self.page_repo.get_page(page_id)
        if page is None:
            raise LookupError("Page not found")
        await self.cleanup_repo.enqueue(page_id)
        return {"page_id": page_id, "url": page.url, "status": "deleting"}
