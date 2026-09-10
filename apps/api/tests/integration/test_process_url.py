"""Integration tests for persistent URL processing jobs."""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from grimoire_api.models.database import JobStatus, PageStatus, ProcessingStep
from grimoire_api.models.external import FetchedDocument, SummaryResult
from grimoire_api.repositories.database import DatabaseConnection
from grimoire_api.repositories.file_repository import FileRepository
from grimoire_api.repositories.job_repository import JobRepository
from grimoire_api.repositories.log_repository import LogRepository
from grimoire_api.repositories.page_repository import PageRepository
from grimoire_api.services.base_processor import BaseProcessorService
from grimoire_api.services.job_worker import JobWorker


def _build_worker(
    db: DatabaseConnection,
    storage_path: str,
    *,
    jina_client: AsyncMock | None = None,
) -> tuple[JobWorker, AsyncMock, AsyncMock, AsyncMock]:
    page_repo = PageRepository(db)
    job_repo = JobRepository(db)
    log_repo = LogRepository(db)
    file_repo = FileRepository(storage_path)
    jina = jina_client or AsyncMock()
    jina.fetch_content.return_value = FetchedDocument(
        title="Test Page Title",
        content="This is test content for integration testing.",
        source_url="https://example.com/test",
        raw_response={
            "data": {
                "title": "Test Page Title",
                "content": "This is test content for integration testing.",
            }
        },
    )
    llm = AsyncMock()
    llm.generate_summary_keywords.return_value = SummaryResult(
        summary="Test summary for integration testing",
        keywords=["test", "integration", "example"],
    )
    vectorizer = AsyncMock()
    processor = BaseProcessorService(
        jina,
        llm,
        vectorizer,
        page_repo,
        log_repo,
        file_repo,
        job_repo,
    )
    return (
        JobWorker(job_repo, page_repo, log_repo, processor),
        jina,
        llm,
        vectorizer,
    )


async def _run_queued_job(worker: JobWorker) -> None:
    job = await worker.job_repo.claim_next()
    assert job is not None
    await worker._execute(job)


async def test_process_url_persists_queued_job(
    integration_client: TestClient, temp_db: DatabaseConnection
) -> None:
    response = integration_client.post(
        "/api/v1/process-url",
        json={"url": "https://example.com/queued", "memo": "Test memo"},
    )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "queued"
    assert data["job_id"] is not None
    job = await JobRepository(temp_db).get_latest_for_page(data["page_id"])
    assert job is not None
    assert job.id == data["job_id"]
    assert job.status == JobStatus.QUEUED


async def test_duplicate_url_reuses_page_without_another_job(
    integration_client: TestClient, temp_db: DatabaseConnection
) -> None:
    url = "https://example.com/duplicate"
    first = integration_client.post("/api/v1/process-url", json={"url": url})
    second = integration_client.post("/api/v1/process-url", json={"url": url})

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["status"] == "already_exists"
    assert second.json()["page_id"] == first.json()["page_id"]
    jobs = await temp_db.fetch_all("SELECT id FROM jobs")
    assert len(jobs) == 1


async def test_independent_worker_completes_queued_job(
    integration_client: TestClient,
    temp_db: DatabaseConnection,
    temp_storage: str,
) -> None:
    response = integration_client.post(
        "/api/v1/process-url",
        json={"url": "https://example.com/test", "memo": "Test memo"},
    )
    page_id = response.json()["page_id"]
    worker, jina, llm, vectorizer = _build_worker(temp_db, temp_storage)

    await _run_queued_job(worker)

    page = await worker.page_repo.get_page(page_id)
    job = await worker.job_repo.get_latest_for_page(page_id)
    assert page is not None and page.status == PageStatus.SUCCEEDED
    assert page.last_success_step == ProcessingStep.COMPLETED
    assert page.title == "Test Page Title"
    assert page.summary == "Test summary for integration testing"
    assert job is not None and job.status == JobStatus.SUCCEEDED
    jina.fetch_content.assert_awaited_once_with("https://example.com/test")
    llm.generate_summary_keywords.assert_awaited_once_with(page_id)
    vectorizer.vectorize_content.assert_awaited_once_with(page_id)

    status_response = integration_client.get(f"/api/v1/process-status/{page_id}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "completed"


async def test_independent_worker_persists_external_service_failure(
    integration_client: TestClient,
    temp_db: DatabaseConnection,
    temp_storage: str,
) -> None:
    response = integration_client.post(
        "/api/v1/process-url", json={"url": "https://example.com/jina-error"}
    )
    page_id = response.json()["page_id"]
    jina = AsyncMock()
    jina.fetch_content.side_effect = RuntimeError("Jina API error")
    worker, _, llm, vectorizer = _build_worker(temp_db, temp_storage, jina_client=jina)

    await _run_queued_job(worker)

    page = await worker.page_repo.get_page(page_id)
    job = await worker.job_repo.get_latest_for_page(page_id)
    assert page is not None and page.status == PageStatus.FAILED
    assert job is not None and job.status == JobStatus.FAILED
    assert job.error_message == "Jina API error"
    llm.generate_summary_keywords.assert_not_awaited()
    vectorizer.vectorize_content.assert_not_awaited()


def test_process_status_not_found(integration_client: TestClient) -> None:
    response = integration_client.get("/api/v1/process-status/99999")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_process_url_requires_valid_url(integration_client: TestClient) -> None:
    invalid = integration_client.post(
        "/api/v1/process-url", json={"url": "invalid-url"}
    )
    missing = integration_client.post("/api/v1/process-url", json={})

    assert invalid.status_code == 422
    assert missing.status_code == 422
