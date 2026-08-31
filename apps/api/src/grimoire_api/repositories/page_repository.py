"""Page repository."""

import json
from collections.abc import Awaitable, Callable

import aiosqlite

from ..models.database import Page, PageStatus, ProcessingStep
from ..utils.datetime import as_utc, utc_isoformat, utc_now_isoformat
from ..utils.exceptions import DatabaseError, RepairDeletionConflictError
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
            INSERT INTO pages (url, title, memo, status, created_at, updated_at)
            VALUES (?, ?, ?, 'queued', ?, ?)
            """
            now = utc_now_isoformat()
            lastrowid = await self.db.execute(query, (url, title, memo, now, now))
            return lastrowid or 0
        except Exception as e:
            raise DatabaseError(f"Failed to create page: {str(e)}")

    async def create_page_with_initial_job(
        self, url: str, title: str, memo: str | None = None
    ) -> tuple[int, int, int]:
        """Page・初期ジョブ・投入イベントを原子的に作成する."""
        try:
            async with self.db.connect() as conn:
                try:
                    await conn.execute("BEGIN IMMEDIATE")
                    now = utc_now_isoformat()
                    page_cursor = await conn.execute(
                        """
                        INSERT INTO pages
                            (url, title, memo, status, created_at, updated_at)
                        VALUES (?, ?, ?, 'queued', ?, ?)
                        """,
                        (url, title, memo, now, now),
                    )
                    page_id = int(page_cursor.lastrowid or 0)

                    job_cursor = await conn.execute(
                        """
                        INSERT INTO jobs
                            (page_id, kind, status, start_step, created_at)
                        VALUES (?, 'initial', 'queued', 'download', ?)
                        """,
                        (page_id, now),
                    )
                    job_id = int(job_cursor.lastrowid or 0)
                    log_cursor = await conn.execute(
                        """INSERT INTO process_logs
                            (page_id, job_id, attempt, url, status, created_at)
                        VALUES (?, ?, 0, ?, 'job_queued', ?)""",
                        (page_id, job_id, url, now),
                    )
                    log_id = int(log_cursor.lastrowid or 0)
                    await conn.commit()
                    return page_id, log_id, job_id
                except Exception:
                    await conn.rollback()
                    raise
        except Exception as e:
            raise DatabaseError(
                f"Failed to create page with initial job: {str(e)}"
            ) from e

    async def get_page(self, page_id: int) -> Page | None:
        """ページ取得."""
        try:
            query = """
            SELECT id, url, title, memo, summary, keywords, weaviate_id,
                   last_success_step, status, created_at, updated_at
            FROM pages WHERE id = ?
            """
            result = await self.db.fetch_one(query, (page_id,))
            if result:
                return self._row_to_page(result)
            return None
        except Exception as e:
            raise DatabaseError(f"Failed to get page: {str(e)}")

    async def get_pages_by_ids(self, page_ids: list[int]) -> dict[int, Page]:
        """複数ページをIDで一括取得する."""
        if not page_ids:
            return {}
        try:
            placeholders = ", ".join("?" for _ in page_ids)
            query = f"""
            SELECT id, url, title, memo, summary, keywords, weaviate_id,
                   last_success_step, status, created_at, updated_at
            FROM pages WHERE id IN ({placeholders})
            """
            results = await self.db.fetch_all(query, tuple(page_ids))
            pages = [self._row_to_page(row) for row in results]
            return {page.id: page for page in pages if page.id is not None}
        except Exception as e:
            raise DatabaseError(f"Failed to get pages by IDs: {str(e)}")

    async def get_searchable_pages_by_ids(
        self,
        page_ids: list[int],
        filters: dict | None = None,
        exclude_keywords: list[str] | None = None,
    ) -> dict[int, Page]:
        """候補IDから検索可能かつページ属性に合うページを取得する."""
        if not page_ids:
            return {}

        unique_page_ids = list(dict.fromkeys(page_ids))
        placeholders = ", ".join("?" for _ in unique_page_ids)
        conditions = [f"id IN ({placeholders})", "status = ?"]
        params: list[object] = [*unique_page_ids, PageStatus.SUCCEEDED.value]
        filters = filters or {}

        url = filters.get("url")
        if url:
            conditions.append("url LIKE ?")
            params.append(f"%{url}%")

        keywords = filters.get("keywords")
        if isinstance(keywords, str):
            keywords = [keywords] if keywords.strip() else []
        elif keywords is None:
            keywords = []
        else:
            keywords = list(keywords)

        valid_keywords = [str(keyword).strip() for keyword in keywords if keyword]
        if valid_keywords:
            keyword_conditions = []
            for keyword in valid_keywords:
                keyword_conditions.append(
                    "EXISTS (SELECT 1 FROM json_each(pages.keywords) "
                    "WHERE json_each.value = ?)"
                )
                params.append(keyword)
            conditions.append(f"({' OR '.join(keyword_conditions)})")

        date_from = filters.get("date_from")
        if date_from:
            conditions.append("created_at >= ?")
            params.append(utc_isoformat(date_from))
        date_to = filters.get("date_to")
        if date_to:
            conditions.append("created_at <= ?")
            params.append(utc_isoformat(date_to))

        valid_excludes = [
            keyword.strip()
            for keyword in (exclude_keywords or [])
            if keyword and keyword.strip()
        ]
        for keyword in valid_excludes:
            conditions.append(
                "NOT EXISTS (SELECT 1 FROM json_each(pages.keywords) "
                "WHERE json_each.value = ?)"
            )
            params.append(keyword)

        try:
            query = f"""
            SELECT id, url, title, memo, summary, keywords, weaviate_id,
                   last_success_step, status, created_at, updated_at
            FROM pages WHERE {" AND ".join(conditions)}
            """
            rows = await self.db.fetch_all(query, tuple(params))
            pages = [self._row_to_page(row) for row in rows]
            return {page.id: page for page in pages if page.id is not None}
        except Exception as e:
            raise DatabaseError(f"Failed to filter searchable pages: {str(e)}")

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
                    utc_now_isoformat(),
                    page_id,
                ),
            )
        except Exception as e:
            raise DatabaseError(f"Failed to update summary/keywords: {str(e)}")

    async def update_page_title(self, page_id: int, title: str) -> None:
        """ページタイトル更新."""
        try:
            query = "UPDATE pages SET title = ?, updated_at = ? WHERE id = ?"
            await self.db.execute(query, (title, utc_now_isoformat(), page_id))
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
            await self.db.execute(query, (step, utc_now_isoformat(), page_id))
        except Exception as e:
            raise DatabaseError(f"Failed to update success step: {str(e)}")

    async def update_status(self, page_id: int, status: PageStatus) -> None:
        """ページの現在状態を更新する."""
        try:
            await self.db.execute(
                "UPDATE pages SET status=?, updated_at=? WHERE id=?",
                (status.value, utc_now_isoformat(), page_id),
            )
        except Exception as e:
            raise DatabaseError(f"Failed to update page status: {e}")

    async def update_url_if_current(
        self, page_id: int, current_url: str, new_url: str
    ) -> bool:
        """現在URLが一致する場合だけURLを更新して検索対象外にする."""
        try:
            async with self.db.connect() as conn:
                await conn.execute("BEGIN IMMEDIATE")
                duplicate = await (
                    await conn.execute(
                        "SELECT id FROM pages WHERE url=? AND id<>?", (new_url, page_id)
                    )
                ).fetchone()
                if duplicate:
                    await conn.rollback()
                    raise DatabaseError("URL already belongs to another page")
                cursor = await conn.execute(
                    """UPDATE pages SET url=?, status='failed', updated_at=?
                    WHERE id=? AND url=?""",
                    (new_url, utc_now_isoformat(), page_id, current_url),
                )
                await conn.commit()
                return cursor.rowcount == 1
        except DatabaseError:
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to update page URL: {e}") from e

    async def update_title_and_step(
        self, page_id: int, title: str, step: ProcessingStep
    ) -> None:
        """タイトルと成功ステップをアトミックに更新."""
        _step_sql = (
            "UPDATE pages SET last_success_step = ?, updated_at = ? WHERE id = ?"
        )
        try:
            now = utc_now_isoformat()
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
            now = utc_now_isoformat()
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
            now = utc_now_isoformat()
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
            await self.db.execute(query, (utc_now_isoformat(), page_id))
        except Exception as e:
            raise DatabaseError(f"Failed to clear weaviate_id: {str(e)}")

    async def delete_pending_repair_page(
        self,
        page_id: int,
        external_cleanup: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """状態検証から外部・SQLite削除までを排他制御する."""
        try:
            async with self.db.connect() as conn:
                await conn.execute("BEGIN IMMEDIATE")
                page = await (
                    await conn.execute("SELECT id FROM pages WHERE id=?", (page_id,))
                ).fetchone()
                if page is None:
                    await conn.rollback()
                    raise LookupError("Page not found")
                repair = await (
                    await conn.execute(
                        "SELECT status FROM repair_cases WHERE page_id=?", (page_id,)
                    )
                ).fetchone()
                if repair is None or repair[0] != "pending":
                    await conn.rollback()
                    raise RepairDeletionConflictError(
                        "Only pages with a pending repair case can be deleted"
                    )
                active_job = await (
                    await conn.execute(
                        "SELECT 1 FROM jobs WHERE page_id=? "
                        "AND status IN ('queued', 'running') LIMIT 1",
                        (page_id,),
                    )
                ).fetchone()
                if active_job is not None:
                    await conn.rollback()
                    raise RepairDeletionConflictError(
                        "Page has a queued or running job"
                    )
                if external_cleanup is not None:
                    await external_cleanup()
                for table in ("process_logs", "jobs", "repair_cases"):
                    await conn.execute(
                        f"DELETE FROM {table} WHERE page_id=?", (page_id,)
                    )
                await conn.execute("DELETE FROM pages WHERE id=?", (page_id,))
                await conn.commit()
        except (LookupError, RepairDeletionConflictError):
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to delete repair page: {e}") from e

    async def get_all_pages(self, limit: int = 100, offset: int = 0) -> list[Page]:
        """全ページ取得."""
        try:
            query = """
            SELECT id, url, title, memo, summary, keywords, weaviate_id,
                   last_success_step, status, created_at, updated_at
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
                   last_success_step, status, created_at, updated_at
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
                   last_success_step, status, created_at, updated_at
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
                   last_success_step, status, created_at, updated_at
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
            return "WHERE status = 'succeeded'"
        elif status_filter == "processing":
            return "WHERE status IN ('queued', 'processing')"
        elif status_filter == "failed":
            return "WHERE status = 'failed'"
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
            created_at=as_utc(row["created_at"]),
            updated_at=as_utc(row["updated_at"]),
            weaviate_id=row["weaviate_id"],
            last_success_step=(
                ProcessingStep(row["last_success_step"])
                if "last_success_step" in row.keys() and row["last_success_step"]
                else None
            ),
            status=PageStatus(row["status"]),
        )
