"""URL processing service."""

from typing import Any

from ..models.database import PageStatus
from ..repositories.page_repository import PageRepository
from ..utils.datetime import utc_isoformat
from ..utils.exceptions import (
    DuplicateUrlError,
    GrimoireAPIError,
    ResourceNotFoundError,
)


class UrlProcessorService:
    """SQLite-backed URL job registration and status service."""

    def __init__(
        self,
        page_repo: PageRepository,
    ):
        """初期化."""
        self.page_repo = page_repo

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

            # 1. ページ・開始ログ・初期ジョブを原子的に作成
            page_id, log_id, job_id = await self.page_repo.create_page_with_initial_job(
                url=url, title="Processing...", memo=memo or ""
            )

            return {
                "status": "prepared",
                "page_id": page_id,
                "log_id": log_id,
                "job_id": job_id,
                "message": "Processing prepared",
            }

        except DuplicateUrlError:
            # 事前チェック後の並行作成競合をalready_existsとして返す
            existing_page_id = await self.page_repo.get_page_by_url(url)
            if existing_page_id:
                return {
                    "status": "already_exists",
                    "page_id": existing_page_id,
                    "message": "URL already exists in the database",
                }
            raise GrimoireAPIError("URL processing preparation failed") from None
        except Exception as e:
            raise GrimoireAPIError(f"URL processing preparation failed: {str(e)}")

    async def get_processing_status(self, page_id: int) -> dict[str, Any]:
        """処理状況取得."""
        try:
            page = await self.page_repo.get_page(page_id)
            if not page:
                raise ResourceNotFoundError(f"Page {page_id} not found")

            return {
                "status": (
                    "completed"
                    if page.status == PageStatus.SUCCEEDED
                    else page.status.value
                ),
                "message": "Processing status retrieved",
                "page": {
                    "id": page.id,
                    "url": page.url,
                    "title": page.title,
                    "memo": page.memo,
                    "summary": page.summary,
                    "keywords": page.keywords,
                    "created_at": utc_isoformat(page.created_at),
                },
            }

        except ResourceNotFoundError:
            raise
        except Exception as e:
            return {"status": "error", "message": str(e)}
