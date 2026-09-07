"""Processing and deletion registrations must be mutually exclusive."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from grimoire_api.models.database import JobKind, PageStatus, PipelineStartStep
from grimoire_api.repositories.cleanup_job_repository import CleanupJobRepository
from grimoire_api.repositories.job_repository import JobRepository
from grimoire_api.services.retry_service import RetryService
from grimoire_api.utils.exceptions import (
    PageDeletionConflictError,
    ResourceConflictError,
)


@pytest.mark.parametrize("kind", [JobKind.RETRY, JobKind.REPROCESS])
@pytest.mark.parametrize(
    ("cleanup_state", "page_status"),
    [(None, PageStatus.DELETING)]
    + [
        (state, status)
        for state in ("queued", "running")
        for status in (PageStatus.DELETING, PageStatus.FAILED)
    ],
)
async def test_registration_rejects_deletion_without_mutation(
    temp_db, page_repo, set_page_status, kind, cleanup_state, page_status
):
    page_id = await page_repo.create_page("https://deleting.example", "delete")
    if cleanup_state is not None:
        cleanup = CleanupJobRepository(temp_db)
        await cleanup.enqueue(page_id)
        if cleanup_state == "running":
            await cleanup.claim_next()
    await set_page_status(page_repo, page_id, page_status)
    before = await page_repo.get_page(page_id)
    cleanup_before = await temp_db.fetch_all("SELECT * FROM cleanup_jobs")

    with pytest.raises(ResourceConflictError, match="being deleted"):
        await JobRepository(temp_db).enqueue(page_id, kind, PipelineStartStep.DOWNLOAD)

    assert await page_repo.get_page(page_id) == before
    assert await temp_db.fetch_all("SELECT * FROM cleanup_jobs") == cleanup_before
    assert await temp_db.fetch_all("SELECT * FROM jobs") == []
    assert await temp_db.fetch_all("SELECT * FROM process_logs") == []


@pytest.mark.parametrize("operation", ["retry_single_page", "reprocess_page"])
async def test_service_rechecks_deletion_after_reading_page(
    temp_db, page_repo, set_page_status, operation
):
    page_id = await page_repo.create_page("https://stale.example", "stale")
    await set_page_status(page_repo, page_id, PageStatus.FAILED)
    stale_page = await page_repo.get_page(page_id)
    await CleanupJobRepository(temp_db).enqueue(page_id)
    service = RetryService(
        AsyncMock(get_page=AsyncMock(return_value=stale_page)), JobRepository(temp_db)
    )

    with pytest.raises(ResourceConflictError, match="being deleted"):
        await getattr(service, operation)(page_id)
    assert await temp_db.fetch_all("SELECT * FROM jobs") == []
    assert (await page_repo.get_page(page_id)).status == PageStatus.DELETING


@pytest.mark.parametrize("kind", [JobKind.RETRY, JobKind.REPROCESS])
@pytest.mark.parametrize("first", ["processing", "deletion", "concurrent"])
async def test_processing_and_deletion_cannot_both_register(
    temp_db, page_repo, set_page_status, kind, first
):
    page_id = await page_repo.create_page("https://race.example", "race")
    await set_page_status(page_repo, page_id, PageStatus.FAILED)
    jobs = JobRepository(temp_db)
    cleanup = CleanupJobRepository(temp_db)

    async def process():
        return await jobs.enqueue(page_id, kind, PipelineStartStep.DOWNLOAD)

    if first == "processing":
        await process()
        with pytest.raises(PageDeletionConflictError):
            await cleanup.enqueue(page_id)
    elif first == "deletion":
        await cleanup.enqueue(page_id)
        with pytest.raises(ResourceConflictError):
            await process()
    else:
        results = await asyncio.gather(
            process(), cleanup.enqueue(page_id), return_exceptions=True
        )
        assert sum(isinstance(result, Exception) for result in results) == 1
        assert any(
            isinstance(result, (ResourceConflictError, PageDeletionConflictError))
            for result in results
        )

    processing_job = await jobs.claim_next()
    cleanup_job = await cleanup.claim_next()
    assert (processing_job is None) != (cleanup_job is None)
    page = await page_repo.get_page(page_id)
    assert page.status == (
        PageStatus.PROCESSING if processing_job else PageStatus.DELETING
    )
