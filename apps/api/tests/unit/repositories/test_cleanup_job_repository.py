"""Tests for persistent page cleanup jobs."""

import pytest
from grimoire_api.models.database import CleanupJobStatus, PageStatus
from grimoire_api.repositories.cleanup_job_repository import CleanupJobRepository
from grimoire_api.repositories.repair_repository import RepairRepository
from grimoire_api.utils.exceptions import RepairDeletionConflictError


async def _pending_page(page_repo, temp_db, url: str = "https://delete.example") -> int:
    page_id = await page_repo.create_page(url, "delete")
    await RepairRepository(temp_db).upsert_pending(
        page_id, "scan", [{"code": "invalid", "detail": "bad"}]
    )
    return page_id


async def test_enqueue_is_idempotent_and_marks_page_deleting(
    temp_db, page_repo
) -> None:
    page_id = await _pending_page(page_repo, temp_db)
    repo = CleanupJobRepository(temp_db)

    first = await repo.enqueue(page_id)
    second = await repo.enqueue(page_id)

    page = await page_repo.get_page(page_id)
    assert first.id == second.id
    assert page is not None and page.status == PageStatus.DELETING


async def test_enqueue_rejects_page_without_pending_repair(temp_db, page_repo) -> None:
    page_id = await page_repo.create_page("https://keep.example", "keep")
    with pytest.raises(RepairDeletionConflictError, match="pending repair"):
        await CleanupJobRepository(temp_db).enqueue(page_id)


async def test_running_job_is_recovered_after_interruption(temp_db, page_repo) -> None:
    page_id = await _pending_page(page_repo, temp_db)
    repo = CleanupJobRepository(temp_db)
    await repo.enqueue(page_id)
    claimed = await repo.claim_next()
    assert claimed is not None and claimed.status == CleanupJobStatus.RUNNING

    await repo.recover_running()
    recovered = await repo.claim_next()

    assert recovered is not None
    assert recovered.id == claimed.id
    assert recovered.attempt == 2
