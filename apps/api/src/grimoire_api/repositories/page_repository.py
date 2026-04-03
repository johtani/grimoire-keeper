"""Page repository."""

import json
from datetime import datetime

from ..models.database import Page
from ..utils.exceptions import DatabaseError
from .database import DatabaseConnection
from .file_repository import FileRepository


class PageRepository:
    """ページリポジトリ."""

    def __init__(
        self,
        db: DatabaseConnection | None = None,
        file_repo: FileRepository | None = None,
    ):
        """初期化.

        Args:
            db: データベース接続
            file_repo: ファイルリポジトリ
        """
        self.db = db or DatabaseConnection()
        self.file_repo = file_repo or FileRepository()

    async def get_page_by_url(self, url: str) -> Page | None:
        """URLでページ取得."""
        try:
            query = "SELECT * FROM pages WHERE url = ?"
            result = await self.db.fetch_one(query, (url,))
            if result:
                return self._row_to_page(result)
            return None
        except Exception as e:
            raise DatabaseError(f"Failed to get page by URL: {str(e)}")

    async def create_page(self, url: str, title: str, memo: str | None = None) -> int:
        """Page作成."""
        try:
            query = """
            INSERT INTO pages (url, title, memo, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """
            now = datetime.now()
            lastrowid = await self.db.execute(query, (url, title, memo, now, now))
            return lastrowid or 0
        except Exception as e:
            raise DatabaseError(f"Failed to create page: {str(e)}")

    async def get_page(self, page_id: int) -> Page | None:
        """ページ取得."""
        try:
            query = "SELECT * FROM pages WHERE id = ?"
            result = await self.db.fetch_one(query, (page_id,))
            if result:
                return self._row_to_page(result)
            return None
        except Exception as e:
            raise DatabaseError(f"Failed to get page: {str(e)}")

    async def update_summary_keywords(
        self, page_id: int, summary: str, keywords: list[str]
    ) -> None:
        """要約・キーワード更新."""
        try:
            query = """
            UPDATE pages
            SET summary = ?, keywords = ?, updated_at = ?
            WHERE id = ?
            """
            await self.db.execute(
                query,
                (
                    summary,
                    json.dumps(keywords, ensure_ascii=False),
                    datetime.now(),
                    page_id,
                ),
            )
        except Exception as e:
            raise DatabaseError(f"Failed to update summary/keywords: {str(e)}")

    async def update_page_title(self, page_id: int, title: str) -> None:
        """ページタイトル更新."""
        try:
            query = "UPDATE pages SET title = ?, updated_at = ? WHERE id = ?"
            await self.db.execute(query, (title, datetime.now(), page_id))
        except Exception as e:
            raise DatabaseError(f"Failed to update page title: {str(e)}")

    async def update_weaviate_id(self, page_id: int, weaviate_id: str) -> None:
        """Weaviate ID更新."""
        try:
            query = "UPDATE pages SET weaviate_id = ? WHERE id = ?"
            await self.db.execute(query, (weaviate_id, page_id))
        except Exception as e:
            raise DatabaseError(f"Failed to update weaviate_id: {str(e)}")

    async def update_success_step(self, page_id: int, step: str) -> None:
        """成功ステップ更新."""
        try:
            query = (
                "UPDATE pages SET last_success_step = ?, updated_at = ? WHERE id = ?"
            )
            await self.db.execute(query, (step, datetime.now(), page_id))
        except Exception as e:
            raise DatabaseError(f"Failed to update success step: {str(e)}")

    async def save_json_file(self, page_id: int, data: dict) -> None:
        """JSONファイル保存."""
        await self.file_repo.save_json_file(page_id, data)

    async def get_all_pages(self, limit: int = 100, offset: int = 0) -> list[Page]:
        """全ページ取得."""
        try:
            query = """
            SELECT * FROM pages
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """
            results = await self.db.fetch_all(query, (limit, offset))
            return [self._row_to_page(row) for row in results]
        except Exception as e:
            raise DatabaseError(f"Failed to get all pages: {str(e)}")

    async def get_by_id(self, page_id: int) -> dict | None:
        """ページIDで取得."""
        page = await self.get_page(page_id)
        if not page:
            return None

        error_message = await self._get_latest_error(page_id)

        error_check = await self.db.fetch_one(
            "SELECT 1 FROM process_logs WHERE page_id = ? AND status = 'failed'",
            (page_id,),
        )
        status = self._compute_page_status(
            page.summary, page.weaviate_id, bool(error_check)
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

    async def _get_latest_error(self, page_id: int) -> str | None:
        """最新のエラーメッセージを取得."""
        try:
            query = """
            SELECT error_message FROM process_logs
            WHERE page_id = ? AND status = 'failed' AND error_message IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 1
            """
            result = await self.db.fetch_one(query, (page_id,))
            return result["error_message"] if result else None
        except Exception:
            return None

    async def get_pages(
        self,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "created_at",
        order: str = "desc",
        status_filter: str | None = None,
    ) -> list[Page]:
        """ページ一覧取得."""
        try:
            where_clause = self._status_where_clause(status_filter)
            params: list = []

            order_clause = f"ORDER BY {sort_by} {order.upper()}"
            query = f"""
            SELECT * FROM pages
            {where_clause}
            {order_clause}
            LIMIT ? OFFSET ?
            """
            params.extend([limit, offset])

            results = await self.db.fetch_all(query, tuple(params))
            return [self._row_to_page(row) for row in results]
        except Exception as e:
            raise DatabaseError(f"Failed to get pages: {str(e)}")

    async def count_pages(self, status_filter: str | None = None) -> int:
        """ページ総数取得."""
        try:
            where_clause = self._status_where_clause(status_filter)

            query = f"SELECT COUNT(*) as total FROM pages {where_clause}"
            result = await self.db.fetch_one(query)
            return result["total"] if result else 0
        except Exception as e:
            raise DatabaseError(f"Failed to count pages: {str(e)}")

    async def list_pages(
        self,
        limit: int = 20,
        offset: int = 0,
        sort: str = "created_at",
        order: str = "desc",
        status_filter: str | None = None,
    ) -> tuple[list[dict], int]:
        """ページ一覧取得 (async)."""
        try:
            where_clause = self._status_where_clause(status_filter)

            count_query = f"SELECT COUNT(*) as total FROM pages {where_clause}"
            count_result = await self.db.fetch_one(count_query)
            total = count_result["total"] if count_result else 0

            order_clause = f"ORDER BY {sort} {order.upper()}"
            query = f"""
            SELECT * FROM pages
            {where_clause}
            {order_clause}
            LIMIT ? OFFSET ?
            """
            results = await self.db.fetch_all(query, (limit, offset))

            pages = []
            for row in results:
                error_check = await self.db.fetch_one(
                    "SELECT 1 FROM process_logs WHERE page_id = ? AND status = 'failed'",  # noqa: E501
                    (row["id"],),
                )
                status = self._compute_page_status(
                    row["summary"], row["weaviate_id"], bool(error_check)
                )

                has_json_file = await self.file_repo.file_exists(row["id"])

                pages.append(
                    {
                        "id": row["id"],
                        "url": row["url"],
                        "title": row["title"],
                        "memo": row["memo"],
                        "summary": row["summary"],
                        "keywords": self._parse_keywords(row["keywords"]),
                        "created_at": datetime.fromisoformat(row["created_at"]),
                        "status": status,
                        "has_json_file": has_json_file,
                    }
                )

            return pages, total
        except Exception as e:
            raise DatabaseError(f"Failed to list pages: {str(e)}")

    async def get_pages_by_status(self, last_success_step: str) -> list[Page]:
        """最後の成功ステップでページを取得."""
        try:
            query = """
            SELECT * FROM pages
            WHERE last_success_step = ?
            ORDER BY created_at ASC
            """
            results = await self.db.fetch_all(query, (last_success_step,))
            return [self._row_to_page(row) for row in results]
        except Exception as e:
            raise DatabaseError(f"Failed to get pages by status: {str(e)}")

    def _compute_page_status(
        self,
        summary: str | None,
        weaviate_id: str | None,
        has_failed_log: bool,
    ) -> str:
        """ページステータスを計算する単一の定義."""
        if summary and weaviate_id:
            return "completed"
        return "failed" if has_failed_log else "processing"

    def _status_where_clause(self, status_filter: str | None) -> str:
        """ステータスフィルター用SQL WHERE句を生成."""
        if status_filter == "completed":
            return "WHERE summary IS NOT NULL AND weaviate_id IS NOT NULL"
        elif status_filter == "processing":
            return """
                    WHERE (summary IS NULL OR weaviate_id IS NULL)
                    AND id NOT IN (
                        SELECT DISTINCT page_id FROM process_logs
                        WHERE status = 'failed' AND page_id IS NOT NULL
                    )
                    """
        elif status_filter == "failed":
            return """
                    WHERE id IN (
                        SELECT DISTINCT page_id FROM process_logs
                        WHERE status = 'failed' AND page_id IS NOT NULL
                    )
                    """
        return ""

    @staticmethod
    def _parse_keywords(keywords_json: str | None) -> list[str]:
        """キーワードJSON文字列をリストに変換."""
        return json.loads(keywords_json) if keywords_json else []

    def _row_to_page(self, row: object) -> Page:
        """行データをPageモデルに変換."""
        return Page(
            id=row["id"],
            url=row["url"],
            title=row["title"],
            memo=row["memo"],
            summary=row["summary"],
            keywords=self._parse_keywords(row["keywords"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            weaviate_id=row["weaviate_id"],
            last_success_step=(
                row["last_success_step"] if "last_success_step" in row.keys() else None
            ),
        )
