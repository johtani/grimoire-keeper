"""Page service — ページ一覧・詳細取得のビジネスロジック."""

import asyncio
from datetime import datetime

from ..repositories.file_repository import FileRepository
from ..repositories.log_repository import LogRepository
from ..repositories.page_repository import PageRepository


class PageService:
    """ページ関連のビジネスロジックを担当するサービス."""

    def __init__(
        self,
        page_repo: PageRepository,
        log_repo: LogRepository,
        file_repo: FileRepository,
    ):
        """初期化.

        Args:
            page_repo: ページリポジトリ
            log_repo: ログリポジトリ
            file_repo: ファイルリポジトリ
        """
        self.page_repo = page_repo
        self.log_repo = log_repo
        self.file_repo = file_repo

    @staticmethod
    def compute_page_status(
        summary: str | None,
        weaviate_id: str | None,
        has_failed_log: bool,
    ) -> str:
        """ページステータスを計算する.

        Args:
            summary: 要約テキスト
            weaviate_id: Weaviate ID
            has_failed_log: failedログが存在するか

        Returns:
            ステータス文字列 ("completed" / "failed" / "processing")
        """
        if summary and weaviate_id:
            return "completed"
        return "failed" if has_failed_log else "processing"

    async def list_pages(
        self,
        limit: int = 20,
        offset: int = 0,
        sort: str = "created_at",
        order: str = "desc",
        status_filter: str | None = None,
    ) -> tuple[list[dict], int]:
        """ステータス付きページ一覧を返す.

        Args:
            limit: 取得件数
            offset: オフセット
            sort: ソートフィールド
            order: ソート順
            status_filter: ステータスフィルター

        Returns:
            (ページ辞書リスト, 総数)
        """
        pages, total = await self.page_repo.list_pages(
            limit=limit,
            offset=offset,
            sort=sort,
            order=order,
            status_filter=status_filter,
        )

        failed_page_ids, existing_json_ids = await asyncio.gather(
            self.log_repo.get_failed_page_ids(),
            self.file_repo.get_existing_page_ids(),
        )

        result = []
        for page in pages:
            status = self.compute_page_status(
                page.summary, page.weaviate_id, page.id in failed_page_ids
            )
            has_json_file = page.id in existing_json_ids
            result.append(
                {
                    "id": page.id,
                    "url": page.url,
                    "title": page.title,
                    "memo": page.memo,
                    "summary": page.summary,
                    "created_at": (
                        page.created_at
                        if isinstance(page.created_at, datetime)
                        else datetime.fromisoformat(str(page.created_at))
                    ),
                    "status": status,
                    "has_json_file": has_json_file,
                }
            )
        return result, total

    async def get_page_detail(self, page_id: int) -> dict | None:
        """ステータス・エラー情報付きページ詳細を返す.

        Args:
            page_id: ページID

        Returns:
            ページ詳細辞書、または None (存在しない場合)
        """
        page = await self.page_repo.get_page(page_id)
        if not page:
            return None

        error_message, has_failed_log_row = await asyncio.gather(
            self.log_repo.get_latest_error(page_id),
            self.log_repo.get_failed_page_ids(),
        )
        has_failed_log = page_id in has_failed_log_row

        status = self.compute_page_status(
            page.summary, page.weaviate_id, has_failed_log
        )

        return {
            "id": page.id,
            "url": page.url,
            "title": page.title,
            "memo": page.memo,
            "summary": page.summary,
            "keywords": page.keywords,
            "created_at": page.created_at,
            "updated_at": page.updated_at,
            "weaviate_id": page.weaviate_id,
            "status": status,
            "error_message": error_message,
            "last_success_step": page.last_success_step,
        }
