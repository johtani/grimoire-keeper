"""Tests for page deletion request handling."""

import pytest
from grimoire_api.models.database import JobKind, PageStatus, PipelineStartStep
from grimoire_api.repositories.cleanup_job_repository import CleanupJobRepository
from grimoire_api.repositories.job_repository import JobRepository
from grimoire_api.repositories.repair_repository import RepairRepository
from grimoire_api.services.page_deletion_service import PageDeletionService
from grimoire_api.utils.exceptions import PageDeletionConflictError


@pytest.fixture
def deletion_service(temp_db, page_repo) -> PageDeletionService:
    return PageDeletionService(page_repo, CleanupJobRepository(temp_db))


async def test_normal_page_deletion_is_accepted(
    deletion_service, page_repo, set_page_status
) -> None:
    page_id = await page_repo.create_page("https://example.com/delete", "delete")
    await set_page_status(page_repo, page_id, PageStatus.SUCCEEDED)

    result = await deletion_service.delete_page(page_id)

    assert result == {
        "page_id": page_id,
        "url": "https://example.com/delete",
        "status": "deleting",
    }
    page = await page_repo.get_page(page_id)
    assert page is not None and page.status == PageStatus.DELETING


async def test_deletion_is_idempotent(
    deletion_service, page_repo, temp_db, set_page_status
) -> None:
    page_id = await page_repo.create_page("https://example.com/repeat", "repeat")
    await set_page_status(page_repo, page_id, PageStatus.FAILED)

    await deletion_service.delete_page(page_id)
    await deletion_service.delete_page(page_id)

    row = await temp_db.fetch_one(
        "SELECT COUNT(*) AS count FROM cleanup_jobs WHERE page_id=?", (page_id,)
    )
    assert row is not None and row["count"] == 1


async def test_pending_repair_page_uses_the_same_deletion_path(
    deletion_service, page_repo, temp_db, set_page_status
) -> None:
    page_id = await page_repo.create_page("https://example.com/repair", "repair")
    await set_page_status(page_repo, page_id, PageStatus.FAILED)
    await RepairRepository(temp_db).upsert_pending(
        page_id, "scan", [{"code": "invalid", "detail": "bad"}]
    )

    result = await deletion_service.delete_page(page_id)

    assert result["status"] == "deleting"


async def test_missing_page_is_rejected(deletion_service) -> None:
    with pytest.raises(LookupError, match="Page not found"):
        await deletion_service.delete_page(999)


async def test_active_processing_job_is_rejected(
    deletion_service, page_repo, temp_db, set_page_status
) -> None:
    page_id = await page_repo.create_page("https://example.com/active", "active")
    await set_page_status(page_repo, page_id, PageStatus.FAILED)
    await JobRepository(temp_db).enqueue(
        page_id, JobKind.REPROCESS, PipelineStartStep.DOWNLOAD
    )

    with pytest.raises(PageDeletionConflictError, match="queued or running"):
        await deletion_service.delete_page(page_id)


async def test_processing_page_state_is_rejected(
    deletion_service, page_repo, set_page_status
) -> None:
    page_id = await page_repo.create_page("https://example.com/processing", "active")
    await set_page_status(page_repo, page_id, PageStatus.PROCESSING)

    with pytest.raises(PageDeletionConflictError, match="processing"):
        await deletion_service.delete_page(page_id)
