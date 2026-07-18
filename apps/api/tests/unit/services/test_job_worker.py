"""Persistent job worker tests."""

from datetime import datetime
from unittest.mock import AsyncMock

from grimoire_api.models.database import (
    Job,
    JobKind,
    JobStatus,
    Page,
    PageStatus,
    PipelineStartStep,
)
from grimoire_api.services.job_worker import JobWorker


def make_job() -> Job:
    return Job(
        id=3,
        page_id=2,
        kind=JobKind.INITIAL,
        status=JobStatus.RUNNING,
        current_step=None,
        start_step=PipelineStartStep.DOWNLOAD,
        attempt=1,
        error_message=None,
        created_at=datetime.now(),
        started_at=datetime.now(),
        finished_at=None,
    )


def make_page() -> Page:
    now = datetime.now()
    return Page(
        id=2,
        url="https://example.com",
        title="title",
        memo=None,
        summary=None,
        keywords=[],
        created_at=now,
        updated_at=now,
        weaviate_id=None,
        status=PageStatus.PROCESSING,
    )


async def test_worker_recovers_on_start() -> None:
    job_repo = AsyncMock()
    worker = JobWorker(job_repo, AsyncMock(), AsyncMock(), AsyncMock())
    job_repo.claim_next.return_value = None

    await worker.start()
    await worker.stop()

    job_repo.recover_running.assert_awaited_once()


async def test_worker_marks_success() -> None:
    job_repo = AsyncMock()
    page_repo = AsyncMock()
    log_repo = AsyncMock()
    processor = AsyncMock()
    page_repo.get_page.return_value = make_page()
    log_repo.create_log.return_value = 9
    worker = JobWorker(job_repo, page_repo, log_repo, processor)

    await worker._execute(3, 2, PipelineStartStep.DOWNLOAD)

    processor._run_pipeline_from.assert_awaited_once_with(
        2, 9, "https://example.com", PipelineStartStep.DOWNLOAD, 3
    )
    job_repo.succeed.assert_awaited_once_with(3, 2)


async def test_worker_records_failure() -> None:
    job_repo = AsyncMock()
    page_repo = AsyncMock()
    log_repo = AsyncMock()
    processor = AsyncMock()
    page_repo.get_page.return_value = make_page()
    log_repo.create_log.return_value = 9
    processor._run_pipeline_from.side_effect = RuntimeError("boom")
    worker = JobWorker(job_repo, page_repo, log_repo, processor)

    await worker._execute(3, 2, PipelineStartStep.DOWNLOAD)

    log_repo.update_status.assert_awaited_once_with(9, "failed", "boom")
    job_repo.fail.assert_awaited_once_with(3, 2, "boom")


async def test_worker_records_failure_when_log_creation_fails() -> None:
    job_repo = AsyncMock()
    page_repo = AsyncMock()
    log_repo = AsyncMock()
    page_repo.get_page.return_value = make_page()
    log_repo.create_log.side_effect = RuntimeError("log unavailable")
    worker = JobWorker(job_repo, page_repo, log_repo, AsyncMock())

    await worker._execute(3, 2, PipelineStartStep.DOWNLOAD)

    log_repo.update_status.assert_not_awaited()
    job_repo.fail.assert_awaited_once_with(3, 2, "log unavailable")
