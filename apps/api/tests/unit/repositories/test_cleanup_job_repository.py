"""Tests for persistent page cleanup jobs."""

import pytest
from grimoire_api.models.database import (
    CleanupJobStatus,
    JobKind,
    PageStatus,
    PipelineStartStep,
)
from grimoire_api.repositories.cleanup_job_repository import CleanupJobRepository
from grimoire_api.repositories.job_repository import JobRepository
from grimoire_api.utils.exceptions import PageDeletionConflictError
from tests.helpers import set_page_status


async def test_enqueue_is_idempotent_and_marks_page_deleting(
    temp_db, page_repo
) -> None:
    page_id = await page_repo.create_page("https://delete.example", "delete")
    await set_page_status(page_repo, page_id, PageStatus.SUCCEEDED)
    repo = CleanupJobRepository(temp_db)

    first = await repo.enqueue(page_id)
    second = await repo.enqueue(page_id)

    page = await page_repo.get_page(page_id)
    assert first.id == second.id
    assert page is not None and page.status == PageStatus.DELETING


async def test_enqueue_rejects_page_with_active_processing_job(
    temp_db, page_repo
) -> None:
    page_id = await page_repo.create_page("https://active.example", "active")
    await set_page_status(page_repo, page_id, PageStatus.FAILED)
    await JobRepository(temp_db).enqueue(
        page_id, JobKind.INITIAL, PipelineStartStep.DOWNLOAD
    )

    with pytest.raises(PageDeletionConflictError, match="queued or running"):
        await CleanupJobRepository(temp_db).enqueue(page_id)


async def test_enqueue_rejects_processing_page_without_active_job(
    temp_db, page_repo
) -> None:
    page_id = await page_repo.create_page("https://processing.example", "processing")
    await set_page_status(page_repo, page_id, PageStatus.PROCESSING)

    with pytest.raises(PageDeletionConflictError, match="processing"):
        await CleanupJobRepository(temp_db).enqueue(page_id)


async def test_running_job_is_recovered_after_interruption(temp_db, page_repo) -> None:
    page_id = await page_repo.create_page("https://recover.example", "recover")
    await set_page_status(page_repo, page_id, PageStatus.SUCCEEDED)
    repo = CleanupJobRepository(temp_db)
    await repo.enqueue(page_id)
    claimed = await repo.claim_next()
    assert claimed is not None and claimed.status == CleanupJobStatus.RUNNING

    await repo.recover_running()
    recovered = await repo.claim_next()

    assert recovered is not None
    assert recovered.id == claimed.id
    assert recovered.attempt == 2
