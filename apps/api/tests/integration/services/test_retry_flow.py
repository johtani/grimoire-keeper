"""Integration tests for persistent retry job registration."""

from grimoire_api.models.database import (
    JobKind,
    JobStatus,
    PageStatus,
    PipelineStartStep,
    ProcessingStep,
)
from grimoire_api.repositories.database import DatabaseConnection
from grimoire_api.repositories.job_repository import JobRepository
from grimoire_api.repositories.page_repository import PageRepository
from grimoire_api.services.retry_service import RetryService


async def _failed_page(
    page_repo: PageRepository,
    set_page_status,
    url: str,
    last_success_step: ProcessingStep | None,
) -> int:
    page_id = await page_repo.create_page(url=url, title="Test Page")
    if last_success_step is not None:
        await page_repo.update_success_step(page_id, last_success_step)
    await set_page_status(page_repo, page_id, PageStatus.FAILED)
    return page_id


async def test_retry_from_downloaded_enqueues_llm_job(
    page_repo: PageRepository,
    temp_db: DatabaseConnection,
    set_page_status,
) -> None:
    page_id = await _failed_page(
        page_repo,
        set_page_status,
        "https://example.com/downloaded",
        ProcessingStep.DOWNLOADED,
    )
    job_repo = JobRepository(temp_db)
    service = RetryService(page_repo, job_repo)

    result = await service.retry_single_page(page_id)

    job = await job_repo.get_latest_for_page(page_id)
    assert result["status"] == "retry_started"
    assert result["restart_from"] == PipelineStartStep.LLM.value
    assert job is not None
    assert job.kind == JobKind.RETRY
    assert job.status == JobStatus.QUEUED
    assert job.start_step == PipelineStartStep.LLM


async def test_retry_from_llm_processed_enqueues_vectorize_job(
    page_repo: PageRepository,
    temp_db: DatabaseConnection,
    set_page_status,
) -> None:
    page_id = await _failed_page(
        page_repo,
        set_page_status,
        "https://example.com/llm-processed",
        ProcessingStep.LLM_PROCESSED,
    )
    job_repo = JobRepository(temp_db)

    result = await RetryService(page_repo, job_repo).retry_single_page(page_id)

    job = await job_repo.get_latest_for_page(page_id)
    assert result["restart_from"] == PipelineStartStep.VECTORIZE.value
    assert job is not None and job.start_step == PipelineStartStep.VECTORIZE


async def test_retry_without_completed_step_enqueues_download_job(
    page_repo: PageRepository,
    temp_db: DatabaseConnection,
    set_page_status,
) -> None:
    page_id = await _failed_page(
        page_repo, set_page_status, "https://example.com/new", None
    )
    job_repo = JobRepository(temp_db)

    result = await RetryService(page_repo, job_repo).retry_single_page(page_id)

    job = await job_repo.get_latest_for_page(page_id)
    assert result["restart_from"] == PipelineStartStep.DOWNLOAD.value
    assert job is not None and job.start_step == PipelineStartStep.DOWNLOAD


async def test_retry_all_failed_persists_one_job_per_page(
    page_repo: PageRepository,
    temp_db: DatabaseConnection,
    set_page_status,
) -> None:
    page_ids = [
        await _failed_page(
            page_repo,
            set_page_status,
            f"https://example.com/failed-{index}",
            ProcessingStep.DOWNLOADED,
        )
        for index in range(2)
    ]
    job_repo = JobRepository(temp_db)

    result = await RetryService(page_repo, job_repo).retry_all_failed()

    assert result["status"] == "batch_retry_started"
    assert result["total_failed_pages"] == 2
    assert result["retry_count"] == 2
    jobs = [await job_repo.get_latest_for_page(page_id) for page_id in page_ids]
    assert all(job is not None and job.status == JobStatus.QUEUED for job in jobs)
