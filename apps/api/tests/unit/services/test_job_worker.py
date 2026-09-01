"""Persistent job worker tests."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from grimoire_api.models.database import (
    Job,
    JobKind,
    JobStatus,
    Page,
    PageStatus,
    PipelineStartStep,
)
from grimoire_api.services.job_worker import JobWorker


def make_job(kind: JobKind = JobKind.INITIAL, attempt: int = 1) -> Job:
    return Job(
        id=3,
        page_id=2,
        kind=kind,
        status=JobStatus.RUNNING,
        current_step=None,
        start_step=PipelineStartStep.DOWNLOAD,
        attempt=attempt,
        error_message=None,
        created_at=datetime.now(UTC),
        started_at=datetime.now(UTC),
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
    job_repo.recover_running.return_value = []
    job_repo.claim_next.return_value = None

    await worker.start()
    await worker.stop()

    job_repo.recover_running.assert_awaited_once()


async def test_worker_counts_recovered_attempt_without_completing_job() -> None:
    job_repo = AsyncMock()
    job_repo.recover_running.return_value = [make_job(attempt=1)]
    job_repo.claim_next.return_value = None
    worker = JobWorker(job_repo, AsyncMock(), AsyncMock(), AsyncMock())

    with (
        patch(
            "grimoire_api.services.job_worker.url_processing_job_attempts"
        ) as attempts,
        patch(
            "grimoire_api.services.job_worker.url_processing_job_completions"
        ) as completions,
    ):
        await worker.start()
        await worker.stop()

    attempts.add.assert_called_once_with(
        1, {"outcome": "interrupted", "job_kind": "initial"}
    )
    completions.add.assert_not_called()


async def test_worker_does_not_claim_after_stop_requested() -> None:
    job_repo = AsyncMock()
    worker = JobWorker(job_repo, AsyncMock(), AsyncMock(), AsyncMock())
    worker._stop_event.set()

    await worker.run()

    job_repo.claim_next.assert_not_awaited()


async def test_worker_updates_heartbeat_before_claim() -> None:
    job_repo = AsyncMock()
    job_repo.claim_next.return_value = None
    heartbeat = MagicMock()
    worker = JobWorker(
        job_repo,
        AsyncMock(),
        AsyncMock(),
        AsyncMock(),
        poll_interval=0.01,
        heartbeat=heartbeat,
    )

    await worker.start()
    await asyncio.sleep(0)
    await worker.stop()

    heartbeat.assert_called()


def test_worker_records_loop_heartbeat_metric() -> None:
    with patch("grimoire_api.services.job_worker.worker_loop_heartbeats") as heartbeats:
        JobWorker.record_loop_heartbeat()

    heartbeats.add.assert_called_once_with(1, {"status": "running"})


async def test_worker_wait_propagates_claim_loop_failure() -> None:
    job_repo = AsyncMock()
    job_repo.claim_next.side_effect = RuntimeError("claim failed")
    worker = JobWorker(job_repo, AsyncMock(), AsyncMock(), AsyncMock())

    await worker.start()

    try:
        await worker.wait()
    except RuntimeError as error:
        assert str(error) == "claim failed"
    else:
        raise AssertionError("claim loop failure must propagate")


async def test_worker_cancels_task_after_stop_timeout() -> None:
    worker = JobWorker(AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock())
    never_finishes = asyncio.Event()
    task = asyncio.create_task(never_finishes.wait())
    worker._task = task

    stopped = await worker.stop(timeout=0.01)
    await asyncio.sleep(0)

    assert not stopped
    assert task.cancelled()
    await worker.wait_stopped()
    assert worker._task is None


async def test_worker_stop_returns_when_task_suppresses_cancellation() -> None:
    worker = JobWorker(AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock())
    release = asyncio.Event()

    async def cancellation_resistant_task() -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await release.wait()

    task = asyncio.create_task(cancellation_resistant_task())
    worker._task = task
    await asyncio.sleep(0)

    stopped = await asyncio.wait_for(worker.stop(timeout=0.01), timeout=0.1)

    assert not stopped
    assert not task.done()
    assert worker._task is task
    release.set()
    await worker.wait_stopped()
    assert worker._task is None


async def test_worker_marks_success() -> None:
    job_repo = AsyncMock()
    page_repo = AsyncMock()
    log_repo = AsyncMock()
    processor = AsyncMock()
    page_repo.get_page.return_value = make_page()
    job_repo.succeed.return_value = True
    worker = JobWorker(job_repo, page_repo, log_repo, processor)

    with (
        patch(
            "grimoire_api.services.job_worker.url_processing_job_attempts"
        ) as attempts,
        patch(
            "grimoire_api.services.job_worker.url_processing_job_completions"
        ) as completions,
    ):
        await worker._execute(make_job())

    processor._run_pipeline_from.assert_awaited_once_with(
        2, "https://example.com", PipelineStartStep.DOWNLOAD, 3
    )
    log_repo.create_log.assert_not_awaited()
    job_repo.succeed.assert_awaited_once_with(3, 2)
    attributes = {"outcome": "succeeded", "job_kind": "initial"}
    attempts.add.assert_called_once_with(1, attributes)
    completions.add.assert_called_once_with(1, attributes)


async def test_worker_records_failure() -> None:
    job_repo = AsyncMock()
    page_repo = AsyncMock()
    log_repo = AsyncMock()
    processor = AsyncMock()
    page_repo.get_page.return_value = make_page()
    processor._run_pipeline_from.side_effect = RuntimeError("boom")
    job_repo.fail.return_value = True
    worker = JobWorker(job_repo, page_repo, log_repo, processor)

    with (
        patch(
            "grimoire_api.services.job_worker.url_processing_job_attempts"
        ) as attempts,
        patch(
            "grimoire_api.services.job_worker.url_processing_job_completions"
        ) as completions,
    ):
        await worker._execute(make_job(kind=JobKind.RETRY, attempt=2))

    log_repo.create_log.assert_not_awaited()
    job_repo.fail.assert_awaited_once_with(3, 2, "boom")
    attributes = {"outcome": "failed", "job_kind": "retry"}
    attempts.add.assert_called_once_with(1, attributes)
    completions.add.assert_called_once_with(1, attributes)


async def test_worker_records_failure_when_page_lookup_fails() -> None:
    job_repo = AsyncMock()
    page_repo = AsyncMock()
    log_repo = AsyncMock()
    page_repo.get_page.return_value = None
    job_repo.fail.return_value = True
    worker = JobWorker(job_repo, page_repo, log_repo, AsyncMock())

    await worker._execute(make_job())

    log_repo.create_log.assert_not_awaited()
    job_repo.fail.assert_awaited_once_with(3, 2, "Page not found")


async def test_worker_does_not_count_duplicate_job_completion() -> None:
    job_repo = AsyncMock()
    page_repo = AsyncMock()
    page_repo.get_page.return_value = make_page()
    job_repo.succeed.return_value = False
    worker = JobWorker(job_repo, page_repo, AsyncMock(), AsyncMock())

    with (
        patch(
            "grimoire_api.services.job_worker.url_processing_job_attempts"
        ) as attempts,
        patch(
            "grimoire_api.services.job_worker.url_processing_job_completions"
        ) as completions,
    ):
        await worker._execute(make_job())

    attempts.add.assert_not_called()
    completions.add.assert_not_called()
