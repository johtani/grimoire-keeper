"""Test-only database helpers."""

from typing import Any

from grimoire_api.models.database import PageStatus
from grimoire_api.repositories.log_repository import LogRepository
from grimoire_api.repositories.page_repository import PageRepository
from grimoire_api.utils.datetime import utc_now_isoformat


async def set_page_status(
    page_repo: PageRepository, page_id: int, status: PageStatus
) -> None:
    """Set persisted page status while arranging a test scenario."""
    await page_repo.db.execute(
        "UPDATE pages SET status=?, updated_at=? WHERE id=?",
        (status.value, utc_now_isoformat(), page_id),
    )


async def get_process_logs(
    log_repo: LogRepository,
    *,
    page_id: int | None = None,
    limit: int = 100,
) -> list[Any]:
    """Read immutable process events for assertions without a production API."""
    where = "WHERE page_id = ?" if page_id is not None else ""
    params = (page_id, limit) if page_id is not None else (limit,)
    return await log_repo.db.fetch_all(
        f"SELECT * FROM process_logs {where} ORDER BY created_at DESC LIMIT ?",
        params,
    )
