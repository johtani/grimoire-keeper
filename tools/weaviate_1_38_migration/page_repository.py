"""Page repository compatible with pre-job and current SQLite schemas."""

from grimoire_api.models.database import Page
from grimoire_api.repositories.page_repository import PageRepository


class MigrationPageRepository(PageRepository):
    """移行前後のpagesスキーマを読み取るリポジトリ."""

    async def _has_status_column(self) -> bool:
        rows = await self.db.fetch_all("PRAGMA table_info(pages)")
        return any(row["name"] == "status" for row in rows)

    async def _completed_page_schema_expressions(self) -> tuple[str, str, str]:
        if await self._has_status_column():
            return "dedupe_key", "status", "status = 'succeeded'"
        completed = (
            "last_success_step = 'completed' "
            "OR (summary IS NOT NULL AND weaviate_id IS NOT NULL)"
        )
        return (
            "NULL",
            f"CASE WHEN {completed} THEN 'succeeded' ELSE 'failed' END",
            completed,
        )

    async def get_page(self, page_id: int) -> Page | None:
        """現在または旧スキーマからページを取得する."""
        dedupe_key, status, _ = await self._completed_page_schema_expressions()
        row = await self.db.fetch_one(
            f"""
            SELECT id, url, {dedupe_key} AS dedupe_key, title, memo, summary,
                   keywords, weaviate_id,
                   last_success_step, {status} AS status, created_at, updated_at
            FROM pages WHERE id = ?
            """,
            (page_id,),
        )
        return self._row_to_page(row) if row else None
