"""RetryService persistent-job tests."""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from grimoire_api.models.database import (
    JobKind,
    Page,
    PageStatus,
    PipelineStartStep,
    ProcessingStep,
)
from grimoire_api.services.retry_service import RetryService
from grimoire_api.utils.exceptions import GrimoireAPIError


def make_page(
    page_id: int = 1,
    status: PageStatus = PageStatus.FAILED,
    last_step: ProcessingStep | None = None,
) -> Page:
    now = datetime.now()
    return Page(
        id=page_id,
        url=f"https://example.com/{page_id}",
        title="title",
        memo=None,
        summary=None,
        keywords=[],
        created_at=now,
        updated_at=now,
        weaviate_id=None,
        last_success_step=last_step,
        status=status,
    )


@pytest.fixture
def dependencies() -> dict[str, AsyncMock]:
    return {
        "jina_client": AsyncMock(),
        "llm_service": AsyncMock(),
        "vectorizer": AsyncMock(),
        "page_repo": AsyncMock(),
        "log_repo": AsyncMock(),
        "file_repo": AsyncMock(),
        "job_repo": AsyncMock(),
    }


@pytest.fixture
def service(dependencies: dict[str, AsyncMock]) -> RetryService:
    return RetryService(**dependencies)


@pytest.mark.parametrize(
    ("last_step", "expected"),
    [
        (None, PipelineStartStep.DOWNLOAD),
        (ProcessingStep.DOWNLOADED, PipelineStartStep.LLM),
        (ProcessingStep.LLM_PROCESSED, PipelineStartStep.VECTORIZE),
        (ProcessingStep.VECTORIZED, PipelineStartStep.VECTORIZE),
        (ProcessingStep.COMPLETED, PipelineStartStep.DOWNLOAD),
    ],
)
async def test_retry_start_step_is_typed(
    service: RetryService,
    dependencies: dict[str, AsyncMock],
    last_step: ProcessingStep | None,
    expected: PipelineStartStep,
) -> None:
    dependencies["page_repo"].get_page.return_value = make_page(last_step=last_step)
    assert await service.get_retry_start_point(1) == expected


async def test_retry_uses_current_page_status(
    service: RetryService, dependencies: dict[str, AsyncMock]
) -> None:
    dependencies["page_repo"].get_page.return_value = make_page(
        status=PageStatus.SUCCEEDED
    )

    result = await service.retry_single_page(1)

    assert result["status"] == "not_failed"
    dependencies["job_repo"].enqueue.assert_not_awaited()


async def test_retry_enqueues_job_without_running_pipeline(
    service: RetryService, dependencies: dict[str, AsyncMock]
) -> None:
    dependencies["page_repo"].get_page.return_value = make_page(
        last_step=ProcessingStep.DOWNLOADED
    )
    dependencies["job_repo"].enqueue.return_value = 10

    result = await service.retry_single_page(1)

    dependencies["job_repo"].enqueue.assert_awaited_once_with(
        1, JobKind.RETRY, PipelineStartStep.LLM
    )
    assert result["job_id"] == 10
    assert result["restart_from"] == "llm"


async def test_reprocess_explicit_step_enqueues_job(
    service: RetryService, dependencies: dict[str, AsyncMock]
) -> None:
    dependencies["page_repo"].get_page.return_value = make_page(
        status=PageStatus.SUCCEEDED
    )
    dependencies["job_repo"].enqueue.return_value = 11

    result = await service.reprocess_page(1, "download")

    dependencies["job_repo"].enqueue.assert_awaited_once_with(
        1, JobKind.REPROCESS, PipelineStartStep.DOWNLOAD
    )
    assert result["job_id"] == 11


async def test_reprocess_rejects_unknown_step(
    service: RetryService, dependencies: dict[str, AsyncMock]
) -> None:
    dependencies["page_repo"].get_page.return_value = make_page()
    with pytest.raises(GrimoireAPIError, match="unknown"):
        await service.reprocess_page(1, "unknown")
    dependencies["job_repo"].enqueue.assert_not_awaited()


async def test_retry_all_uses_only_current_failed_pages(
    service: RetryService, dependencies: dict[str, AsyncMock]
) -> None:
    dependencies["page_repo"].get_pages.return_value = [make_page(1), make_page(2)]
    service.retry_single_page = AsyncMock(side_effect=[{"job_id": 21}, {"job_id": 22}])

    result = await service.retry_all_failed(max_retries=2)

    dependencies["page_repo"].get_pages.assert_awaited_once_with(
        limit=2, status_filter="failed"
    )
    assert result["job_ids"] == [21, 22]
    assert result["retry_count"] == 2


async def test_missing_page_raises_domain_error(
    service: RetryService, dependencies: dict[str, AsyncMock]
) -> None:
    dependencies["page_repo"].get_page.return_value = None
    with pytest.raises(GrimoireAPIError, match="Page 1 not found"):
        await service.get_retry_start_point(1)
