"""Page repository compatible with pre-job and current SQLite schemas."""

from grimoire_api.models.database import Page
from grimoire_api.repositories.page_repository import PageRepository


class MigrationPageRepository(PageRepository):
    """移行前後のpagesスキーマを読み取るリポジトリ."""

    async def _has_status_column(self) -> bool:
        rows = await self.db.fetch_all("PRAGMA table_info(pages)")
        return any(row["name"] == "status" for row in rows)

    async def _schema_expressions(self) -> tuple[str, str]:
        if await self._has_status_column():
            return "status", "status = 'succeeded'"
        completed = (
            "last_success_step = 'completed' "
            "OR (summary IS NOT NULL AND weaviate_id IS NOT NULL)"
        )
        return f"CASE WHEN {completed} THEN 'succeeded' ELSE 'failed' END", completed

    async def count_completed_pages(self) -> int:
        """現在または旧スキーマの成功済みページ数を返す."""
        _, completed = await self._schema_expressions()
        result = await self.db.fetch_one(
            f"SELECT COUNT(*) AS total FROM pages WHERE {completed}"
        )
        return int(result["total"]) if result else 0

    async def get_completed_pages(self, limit: int) -> list[Page]:
        """現在または旧スキーマの成功済みページをID順で返す."""
        status, completed = await self._schema_expressions()
        rows = await self.db.fetch_all(
            f"""
            SELECT id, url, title, memo, summary, keywords, weaviate_id,
                   last_success_step, {status} AS status, created_at, updated_at
            FROM pages
            WHERE {completed}
            ORDER BY id ASC
            LIMIT ?
            """,
            (limit,),
        )
        return [self._row_to_page(row) for row in rows]

    async def get_page(self, page_id: int) -> Page | None:
        """現在または旧スキーマからページを取得する."""
        status, _ = await self._schema_expressions()
        row = await self.db.fetch_one(
            f"""
            SELECT id, url, title, memo, summary, keywords, weaviate_id,
                   last_success_step, {status} AS status, created_at, updated_at
            FROM pages WHERE id = ?
            """,
            (page_id,),
        )
        return self._row_to_page(row) if row else None
