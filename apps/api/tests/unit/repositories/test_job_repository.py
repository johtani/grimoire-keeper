"""Persistent job repository tests."""

import asyncio
from datetime import UTC

import pytest
from grimoire_api.models.database import (
    JobKind,
    JobStatus,
    PipelineStartStep,
    ProcessingStep,
)
from grimoire_api.repositories.job_repository import JobRepository
from grimoire_api.utils.exceptions import DatabaseError


async def test_enqueue_rejects_unknown_page_id(temp_db) -> None:
    repo = JobRepository(temp_db)

    with pytest.raises(
        DatabaseError, match="Failed to enqueue job: FOREIGN KEY constraint failed"
    ):
        await repo.enqueue(999, JobKind.INITIAL, PipelineStartStep.DOWNLOAD)


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
    assert first.created_at.tzinfo is UTC
    assert first.started_at is not None and first.started_at.tzinfo is UTC


async def test_concurrent_claim_does_not_return_same_job(temp_db, page_repo) -> None:
    repo = JobRepository(temp_db)
    page_id = await page_repo.create_page("https://example.com", "title")
    await repo.enqueue(page_id, JobKind.INITIAL, PipelineStartStep.DOWNLOAD)

    first, second = await asyncio.gather(repo.claim_next(), repo.claim_next())

    assert (first is None) != (second is None)


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
    events = await temp_db.fetch_all(
        "SELECT attempt, status FROM process_logs WHERE job_id=? ORDER BY id",
        (claimed.id,),
    )
    assert [(row["attempt"], row["status"]) for row in events] == [
        (0, "job_queued"),
        (1, "job_claimed"),
        (1, "interrupted"),
        (2, "job_claimed"),
    ]


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

    events = await temp_db.fetch_all(
        "SELECT job_id, attempt, status, error_message "
        "FROM process_logs WHERE page_id=? ORDER BY id",
        (page_id,),
    )
    assert [(row["job_id"], row["attempt"], row["status"]) for row in events] == [
        (job_id, 0, "job_queued"),
        (job_id, 1, "job_claimed"),
        (job_id, 1, "failed"),
        (retry_id, 0, "job_queued"),
        (retry_id, 1, "job_claimed"),
        (retry_id, 1, "succeeded"),
    ]
    assert events[2]["error_message"] == "boom"


async def test_step_events_share_claimed_attempt(temp_db, page_repo) -> None:
    repo = JobRepository(temp_db)
    page_id = await page_repo.create_page("https://steps.example.com", "steps")
    job_id = await repo.enqueue(page_id, JobKind.INITIAL, PipelineStartStep.DOWNLOAD)
    claimed = await repo.claim_next()
    assert claimed is not None

    await repo.update_step(job_id, ProcessingStep.DOWNLOADED)
    await repo.update_step(job_id, ProcessingStep.LLM_PROCESSED)
    await repo.update_step(job_id, ProcessingStep.VECTORIZED)
    await repo.update_step(job_id, ProcessingStep.COMPLETED)
    await repo.succeed(job_id, page_id)

    events = await temp_db.fetch_all(
        "SELECT attempt, status FROM process_logs WHERE job_id=? ORDER BY id",
        (job_id,),
    )
    assert [(row["attempt"], row["status"]) for row in events] == [
        (0, "job_queued"),
        (1, "job_claimed"),
        (1, "download_completed"),
        (1, "llm_completed"),
        (1, "vectorize_completed"),
        (1, "pipeline_completed"),
        (1, "succeeded"),
    ]


async def test_has_active_for_page(temp_db, page_repo) -> None:
    repo = JobRepository(temp_db)
    page_id = await page_repo.create_page("https://active.example.com", "title")
    job_id = await repo.enqueue(page_id, JobKind.INITIAL, PipelineStartStep.DOWNLOAD)
    assert await repo.has_active_for_page(page_id)

    claimed = await repo.claim_next()
    assert claimed is not None
    assert await repo.has_active_for_page(page_id)

    await repo.succeed(job_id, page_id)
    assert not await repo.has_active_for_page(page_id)
