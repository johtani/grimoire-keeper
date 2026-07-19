"""Persistent job repository tests."""

import asyncio

import pytest
from grimoire_api.models.database import JobKind, JobStatus, PipelineStartStep
from grimoire_api.repositories.job_repository import JobRepository
from grimoire_api.utils.exceptions import DatabaseError


async def test_active_job_is_unique_per_page(temp_db, page_repo) -> None:
    page_id = await page_repo.create_page("https://example.com", "title")
    repo = JobRepository(temp_db)

    await repo.enqueue(page_id, JobKind.INITIAL, PipelineStartStep.DOWNLOAD)

    with pytest.raises(DatabaseError, match="Failed to enqueue job"):
        await repo.enqueue(page_id, JobKind.RETRY, PipelineStartStep.LLM)


async def test_claim_is_atomic(temp_db, page_repo) -> None:
    repo = JobRepository(temp_db)
    first_page = await page_repo.create_page("https://one.example.com", "one")
    second_page = await page_repo.create_page("https://two.example.com", "two")
    await repo.enqueue(first_page, JobKind.INITIAL, PipelineStartStep.DOWNLOAD)
    await repo.enqueue(second_page, JobKind.INITIAL, PipelineStartStep.DOWNLOAD)

    first, second = await asyncio.gather(repo.claim_next(), repo.claim_next())

    assert first is not None and second is not None
    assert {first.id, second.id} == {1, 2}
    assert first.status == JobStatus.RUNNING
    assert second.status == JobStatus.RUNNING
    assert first.attempt == second.attempt == 1


async def test_recover_running_jobs(temp_db, page_repo) -> None:
    repo = JobRepository(temp_db)
    page_id = await page_repo.create_page("https://example.com", "title")
    await repo.enqueue(page_id, JobKind.INITIAL, PipelineStartStep.DOWNLOAD)
    claimed = await repo.claim_next()
    assert claimed is not None

    assert await repo.recover_running() == 1

    recovered = await repo.claim_next()
    assert recovered is not None
    assert recovered.id == claimed.id
    assert recovered.attempt == 2


async def test_success_and_failure_update_page_status(temp_db, page_repo) -> None:
    repo = JobRepository(temp_db)
    page_id = await page_repo.create_page("https://example.com", "title")
    job_id = await repo.enqueue(page_id, JobKind.INITIAL, PipelineStartStep.DOWNLOAD)
    await repo.claim_next()

    await repo.fail(job_id, page_id, "boom")
    page = await page_repo.get_page(page_id)
    assert page is not None
    assert page.status.value == "failed"

    retry_id = await repo.enqueue(page_id, JobKind.RETRY, PipelineStartStep.DOWNLOAD)
    await repo.claim_next()
    await repo.succeed(retry_id, page_id)
    page = await page_repo.get_page(page_id)
    assert page is not None
    assert page.status.value == "succeeded"
