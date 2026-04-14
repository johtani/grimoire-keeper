"""Page repository."""

import json
from datetime import datetime

import aiosqlite

from ..models.database import Page, ProcessingStep
from ..utils.exceptions import DatabaseError
from .database import DatabaseConnection

_ALLOWED_SORT_FIELDS = frozenset({"id", "url", "title", "created_at", "updated_at"})
_ALLOWED_ORDER = frozenset({"ASC", "DESC"})


class PageRepository:
    """ページリポジトリ."""

    def __init__(
        self,
        db: DatabaseConnection | None = None,
    ):
        """初期化.

        Args:
            db: データベース接続
        """
        self.db = db or DatabaseConnection()

    async def get_page_by_url(self, url: str) -> int | None:
        """URLでページIDを取得."""
        try:
            query = "SELECT id FROM pages WHERE url = ?"
            result = await self.db.fetch_one(query, (url,))
            if result:
                return int(result["id"])
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
            query = """
            SELECT id, url, title, memo, summary, keywords, weaviate_id,
                   last_success_step, created_at, updated_at
            FROM pages WHERE id = ?
            """
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

    async def update_success_step(self, page_id: int, step: ProcessingStep) -> None:
        """成功ステップ更新."""
        try:
            query = (
                "UPDATE pages SET last_success_step = ?, updated_at = ? WHERE id = ?"
            )
            await self.db.execute(query, (step, datetime.now(), page_id))
        except Exception as e:
            raise DatabaseError(f"Failed to update success step: {str(e)}")

    async def update_title_and_step(
        self, page_id: int, title: str, step: ProcessingStep
    ) -> None:
        """タイトルと成功ステップをアトミックに更新."""
        _step_sql = (
            "UPDATE pages SET last_success_step = ?, updated_at = ? WHERE id = ?"
        )
        try:
            now = datetime.now()
            await self.db.execute_transaction(
                [
                    (
                        "UPDATE pages SET title = ?, updated_at = ? WHERE id = ?",
                        (title, now, page_id),
                    ),
                    (_step_sql, (step, now, page_id)),
                ]
            )
        except Exception as e:
            raise DatabaseError(f"Failed to update title and step: {str(e)}")

    async def update_summary_keywords_and_step(
        self, page_id: int, summary: str, keywords: list[str], step: ProcessingStep
    ) -> None:
        """要約・キーワードと成功ステップをアトミックに更新."""
        _step_sql = (
            "UPDATE pages SET last_success_step = ?, updated_at = ? WHERE id = ?"
        )
        _summary_sql = (
            "UPDATE pages SET summary = ?, keywords = ?, updated_at = ? WHERE id = ?"
        )
        try:
            now = datetime.now()
            await self.db.execute_transaction(
                [
                    (
                        _summary_sql,
                        (
                            summary,
                            json.dumps(keywords, ensure_ascii=False),
                            now,
                            page_id,
                        ),
                    ),
                    (_step_sql, (step, now, page_id)),
                ]
            )
        except Exception as e:
            raise DatabaseError(f"Failed to update summary/keywords and step: {str(e)}")

    async def update_weaviate_id_and_step(
        self, page_id: int, weaviate_id: str, step: ProcessingStep
    ) -> None:
        """Weaviate IDと成功ステップをアトミックに更新."""
        _step_sql = (
            "UPDATE pages SET last_success_step = ?, updated_at = ? WHERE id = ?"
        )
        try:
            now = datetime.now()
            await self.db.execute_transaction(
                [
                    (
                        "UPDATE pages SET weaviate_id = ?, updated_at = ? WHERE id = ?",
                        (weaviate_id, now, page_id),
                    ),
                    (_step_sql, (step, now, page_id)),
                ]
            )
        except Exception as e:
            raise DatabaseError(f"Failed to update weaviate_id and step: {str(e)}")

    async def clear_weaviate_id(self, page_id: int) -> None:
        """Weaviate IDをクリア (ロールバック用)."""
        try:
            query = "UPDATE pages SET weaviate_id = NULL, updated_at = ? WHERE id = ?"
            await self.db.execute(query, (datetime.now(), page_id))
        except Exception as e:
            raise DatabaseError(f"Failed to clear weaviate_id: {str(e)}")

    async def get_all_pages(self, limit: int = 100, offset: int = 0) -> list[Page]:
        """全ページ取得."""
        try:
            query = """
            SELECT id, url, title, memo, summary, keywords, weaviate_id,
                   last_success_step, created_at, updated_at
            FROM pages
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """
            results = await self.db.fetch_all(query, (limit, offset))
            return [self._row_to_page(row) for row in results]
        except Exception as e:
            raise DatabaseError(f"Failed to get all pages: {str(e)}")

    @staticmethod
    def _validate_sort_params(sort_field: str, order: str) -> str:
        """ソートパラメータのホワイトリスト検証を行い、正規化した order を返す."""
        if sort_field not in _ALLOWED_SORT_FIELDS:
            raise ValueError(f"Invalid sort field: {sort_field}")
        order_upper = order.upper()
        if order_upper not in _ALLOWED_ORDER:
            raise ValueError(f"Invalid order: {order}")
        return order_upper

    async def get_pages(
        self,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "created_at",
        order: str = "desc",
        status_filter: str | None = None,
    ) -> list[Page]:
        """ページ一覧取得."""
        order_upper = self._validate_sort_params(sort_by, order)
        try:
            where_clause = self._status_where_clause(status_filter)
            params: list = []

            order_clause = f"ORDER BY {sort_by} {order_upper}"
            query = f"""
            SELECT id, url, title, memo, summary, keywords, weaviate_id,
                   last_success_step, created_at, updated_at
            FROM pages
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
    ) -> tuple[list[Page], int]:
        """ページ一覧取得 (Page モデルのリストと総数を返す)."""
        order_upper = self._validate_sort_params(sort, order)
        try:
            where_clause = self._status_where_clause(status_filter)

            count_query = f"SELECT COUNT(*) as total FROM pages {where_clause}"
            count_result = await self.db.fetch_one(count_query)
            total = count_result["total"] if count_result else 0

            order_clause = f"ORDER BY {sort} {order_upper}"
            query = f"""
            SELECT id, url, title, memo, summary, keywords, weaviate_id,
                   last_success_step, created_at, updated_at
            FROM pages
            {where_clause}
            {order_clause}
            LIMIT ? OFFSET ?
            """
            results = await self.db.fetch_all(query, (limit, offset))
            pages = [self._row_to_page(row) for row in results]
            return pages, total
        except Exception as e:
            raise DatabaseError(f"Failed to list pages: {str(e)}")

    async def get_pages_by_status(
        self, last_success_step: ProcessingStep
    ) -> list[Page]:
        """最後の成功ステップでページを取得."""
        try:
            query = """
            SELECT id, url, title, memo, summary, keywords, weaviate_id,
                   last_success_step, created_at, updated_at
            FROM pages
            WHERE last_success_step = ?
            ORDER BY created_at ASC
            """
            results = await self.db.fetch_all(query, (last_success_step,))
            return [self._row_to_page(row) for row in results]
        except Exception as e:
            raise DatabaseError(f"Failed to get pages by status: {str(e)}")

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

    def _row_to_page(self, row: aiosqlite.Row) -> Page:
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
                ProcessingStep(row["last_success_step"])
                if "last_success_step" in row.keys() and row["last_success_step"]
                else None
            ),
        )
