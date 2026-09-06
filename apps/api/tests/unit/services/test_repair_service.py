"""Tests for repair detection and management."""

import asyncio
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from grimoire_api.config import settings
from grimoire_api.models.database import (
    JobKind,
    PageStatus,
    PipelineStartStep,
    RepairStatus,
)
from grimoire_api.repositories.cleanup_job_repository import CleanupJobRepository
from grimoire_api.repositories.database import DatabaseConnection
from grimoire_api.repositories.file_repository import FileRepository
from grimoire_api.repositories.job_repository import JobRepository
from grimoire_api.repositories.log_repository import LogRepository
from grimoire_api.repositories.page_repository import PageRepository
from grimoire_api.repositories.repair_repository import RepairRepository
from grimoire_api.services.deletion_worker import DeletionWorker
from grimoire_api.services.repair_service import RepairService
from grimoire_api.utils.exceptions import (
    DuplicateUrlError,
    RepairDeletionConflictError,
)


@pytest.fixture
def repair_service(
    temp_db: DatabaseConnection, temp_storage: str, tmp_path: Path
) -> RepairService:
    return RepairService(
        PageRepository(temp_db),
        RepairRepository(temp_db),
        FileRepository(temp_storage),
        LogRepository(temp_db),
        JobRepository(temp_db),
        str(tmp_path / "repair-pending.json"),
        cleanup_repo=CleanupJobRepository(temp_db),
    )


async def test_import_report_is_idempotent_and_warns_on_url_mismatch(
    repair_service: RepairService,
) -> None:
    page_id = await repair_service.page_repo.create_page(
        "https://example.com/current", "title"
    )
    repair_service.report_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "repair_pending_count": 1,
                "repair_pending": [
                    {
                        "page_id": page_id,
                        "url": "https://example.com/old%3E",
                        "reasons": [{"code": "jina_http_error", "detail": "code=404"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    first = await repair_service.import_report()
    second = await repair_service.import_report()
    cases = await repair_service.repair_repo.list_cases(RepairStatus.PENDING)

    assert first == {"imported": 1, "missing_pages": 0, "url_mismatches": 1}
    assert second == first
    assert len(cases) == 1
    assert cases[0].reasons[-1]["code"] == "report_url_mismatch"

    await repair_service.repair_repo.resolve(page_id)
    await repair_service.import_report()
    resolved = await repair_service.repair_repo.get_by_page_id(page_id)
    assert resolved and resolved.status == RepairStatus.RESOLVED


async def test_scan_detects_page_56_style_bad_url_and_jina_error(
    repair_service: RepairService,
) -> None:
    page_id = await repair_service.page_repo.create_page(
        "https://example.com/article%3E", "title"
    )
    await repair_service.file_repo.save_json_file(
        page_id,
        {
            "code": 404,
            "data": {"httpStatus": 404, "title": "Not found", "content": "body"},
        },
    )

    result = await repair_service.scan()
    case = await repair_service.repair_repo.get_by_page_id(page_id)

    assert result["pending"] == 1
    assert case is not None
    assert {reason["code"] for reason in case.reasons} == {
        "malformed_url_suffix",
        "jina_http_error",
    }


async def test_scan_detects_missing_and_invalid_json(
    repair_service: RepairService,
) -> None:
    missing_id = await repair_service.page_repo.create_page(
        "https://example.com/missing", "missing"
    )
    invalid_id = await repair_service.page_repo.create_page(
        "https://example.com/invalid", "invalid"
    )
    (repair_service.file_repo.storage_path / f"{invalid_id}.json").write_text(
        "not json", encoding="utf-8"
    )

    await repair_service.scan()

    missing = await repair_service.repair_repo.get_by_page_id(missing_id)
    invalid = await repair_service.repair_repo.get_by_page_id(invalid_id)
    assert missing and missing.reasons[0]["code"] == "missing_json"
    assert invalid and invalid.reasons[0]["code"] == "invalid_json"


async def test_scan_paginates_and_resolves_healthy_case(
    repair_service: RepairService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "REPAIR_SCAN_BATCH_SIZE", 2)
    page_ids = [
        await repair_service.page_repo.create_page(
            f"https://example.com/page-{index}", str(index)
        )
        for index in range(5)
    ]
    for page_id in page_ids:
        await repair_service.file_repo.save_json_file(
            page_id, {"data": {"title": "title", "content": "content"}}
        )
    await repair_service.repair_repo.upsert_pending(
        page_ids[0], "scan", [{"code": "missing_json", "detail": "missing"}]
    )

    result = await repair_service.scan()
    repaired = await repair_service.repair_repo.get_by_page_id(page_ids[0])

    assert result == {"scanned": 5, "pending": 0, "resolved": 1}
    assert repaired is not None and repaired.status == RepairStatus.RESOLVED


async def test_scan_uses_fixed_snapshot_upper_bound(
    repair_service: RepairService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "REPAIR_SCAN_BATCH_SIZE", 1)
    first_id = await repair_service.page_repo.create_page(
        "https://example.com/first", "first"
    )
    await repair_service.file_repo.save_json_file(
        first_id, {"data": {"title": "title", "content": "content"}}
    )
    original = repair_service.page_repo.get_pages_after_id
    added_id: int | None = None

    async def add_page_after_snapshot(
        cursor: int, upper_bound: int, limit: int
    ) -> list:
        nonlocal added_id
        pages = await original(cursor, upper_bound, limit)
        if added_id is None:
            added_id = await repair_service.page_repo.create_page(
                "https://example.com/added", "added"
            )
        return pages

    monkeypatch.setattr(
        repair_service.page_repo, "get_pages_after_id", add_page_after_snapshot
    )

    first = await repair_service.scan()
    second = await repair_service.scan()

    assert first == {"scanned": 1, "pending": 0, "resolved": 0}
    assert second == {"scanned": 2, "pending": 1, "resolved": 0}


async def test_scan_resumes_after_weaviate_failure(
    repair_service: RepairService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "REPAIR_SCAN_BATCH_SIZE", 1)
    page_ids = [
        await repair_service.page_repo.create_page(
            f"https://example.com/resume-{index}", str(index)
        )
        for index in range(2)
    ]
    for page_id in page_ids:
        await repair_service.file_repo.save_json_file(
            page_id, {"data": {"title": "title", "content": "content"}}
        )
        await repair_service.page_repo.update_status(page_id, PageStatus.SUCCEEDED)
    await repair_service.repair_repo.upsert_pending(
        page_ids[0], "scan", [{"code": "missing_json", "detail": "missing"}]
    )

    fetch = MagicMock(
        side_effect=[SimpleNamespace(objects=[object()]), RuntimeError("unavailable")]
    )
    client = MagicMock()
    client.collections.get.return_value.query.fetch_objects = fetch
    repair_service.weaviate_client = client

    with pytest.raises(RuntimeError, match="unavailable"):
        await repair_service.scan()

    checkpoint = await repair_service.page_repo.db.fetch_one(
        "SELECT * FROM repair_scan_state WHERE id=1"
    )
    assert checkpoint is not None
    assert checkpoint["cursor"] == page_ids[0]
    assert checkpoint["scanned"] == 1
    assert checkpoint["resolved"] == 1

    fetch.side_effect = None
    fetch.return_value = SimpleNamespace(objects=[object()])
    result = await repair_service.scan()

    assert result == {"scanned": 2, "pending": 0, "resolved": 1}


async def test_weaviate_checks_have_bounded_concurrency_and_timeout(
    repair_service: RepairService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "REPAIR_SCAN_WEAVIATE_TIMEOUT", 0.2)
    repair_service._weaviate_semaphore = asyncio.Semaphore(2)
    active = maximum = 0
    lock = threading.Lock()

    def fetch_objects(**_kwargs: object) -> SimpleNamespace:
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return SimpleNamespace(objects=[object()])

    client = MagicMock()
    client.collections.get.return_value.query.fetch_objects = fetch_objects
    repair_service.weaviate_client = client

    await asyncio.gather(
        *(repair_service._is_page_registered(index) for index in range(6))
    )
    assert maximum == 2

    monkeypatch.setattr(settings, "REPAIR_SCAN_WEAVIATE_TIMEOUT", 0.001)
    client.collections.get.return_value.query.fetch_objects = (
        lambda **_kwargs: time.sleep(0.02)
    )
    with pytest.raises(TimeoutError):
        await repair_service._is_page_registered(99)


async def test_update_url_marks_page_failed_and_uses_current_url_guard(
    repair_service: RepairService,
) -> None:
    page_id = await repair_service.page_repo.create_page(
        "https://example.com/bad%3E", "title"
    )

    result = await repair_service.update_url(
        page_id, "https://example.com/bad%3E", "https://example.com/good"
    )
    page = await repair_service.page_repo.get_page(page_id)

    assert result["status"] == "failed"
    assert page and page.url == "https://example.com/good"
    assert page.status.value == "failed"
    with pytest.raises(RuntimeError, match="does not match"):
        await repair_service.update_url(
            page_id, "https://example.com/bad%3E", "https://example.com/other"
        )


async def test_update_url_rejects_duplicate(repair_service: RepairService) -> None:
    page_id = await repair_service.page_repo.create_page(
        "https://example.com/one", "one"
    )
    await repair_service.page_repo.create_page("https://example.com/two", "two")

    with pytest.raises(FileExistsError):
        await repair_service.update_url(
            page_id, "https://example.com/one", "https://example.com/two"
        )


async def test_repository_preserves_database_error_for_duplicate(
    repair_service: RepairService,
) -> None:
    first = await repair_service.page_repo.create_page("https://a.example", "a")
    await repair_service.page_repo.create_page("https://b.example", "b")
    with pytest.raises(DuplicateUrlError):
        await repair_service.page_repo.update_url_if_current(
            first, "https://a.example", "https://b.example"
        )


async def test_delete_pending_repair_page_enqueues_without_external_io(
    repair_service: RepairService,
) -> None:
    page_id = await repair_service.page_repo.create_page(
        "https://example.com/delete", "delete"
    )
    await repair_service.file_repo.save_json_file(page_id, {"data": {}})
    await repair_service.repair_repo.upsert_pending(
        page_id, "scan", [{"code": "invalid", "detail": "bad"}]
    )
    await repair_service.log_repo.create_log(
        "https://example.com/delete", "failed", page_id
    )
    vectorizer = AsyncMock()
    repair_service.vectorizer = vectorizer

    result = await repair_service.delete_page(page_id)

    assert result == {
        "page_id": page_id,
        "url": "https://example.com/delete",
        "status": "deleting",
    }
    vectorizer.delete_page_from_index.assert_not_awaited()
    assert await repair_service.file_repo.file_exists(page_id)
    page = await repair_service.page_repo.get_page(page_id)
    assert page is not None and page.status == PageStatus.DELETING

    deletion_worker = DeletionWorker(
        repair_service.cleanup_repo, repair_service.file_repo, vectorizer
    )
    assert await deletion_worker.run_next()
    vectorizer.delete_page_from_index.assert_awaited_once_with(page_id)
    assert not await repair_service.file_repo.file_exists(page_id)
    assert await repair_service.page_repo.get_page(page_id) is None


@pytest.mark.parametrize("resolved", [False, True])
async def test_delete_rejects_missing_or_resolved_repair(
    repair_service: RepairService, resolved: bool
) -> None:
    page_id = await repair_service.page_repo.create_page(
        f"https://example.com/not-pending-{resolved}", "title"
    )
    if resolved:
        await repair_service.repair_repo.upsert_pending(
            page_id, "scan", [{"code": "invalid", "detail": "bad"}]
        )
        await repair_service.repair_repo.resolve(page_id)

    with pytest.raises(RepairDeletionConflictError, match="pending repair"):
        await repair_service.delete_page(page_id)


async def test_delete_rejects_active_job(repair_service: RepairService) -> None:
    page_id = await repair_service.page_repo.create_page(
        "https://example.com/active", "active"
    )
    await repair_service.repair_repo.upsert_pending(
        page_id, "scan", [{"code": "invalid", "detail": "bad"}]
    )
    await repair_service.job_repo.enqueue(
        page_id, JobKind.REPROCESS, PipelineStartStep.DOWNLOAD
    )
    with pytest.raises(RepairDeletionConflictError, match="queued or running"):
        await repair_service.delete_page(page_id)


async def test_delete_failure_can_be_retried(
    repair_service: RepairService,
) -> None:
    page_id = await repair_service.page_repo.create_page(
        "https://example.com/retry-delete", "retry"
    )
    await repair_service.repair_repo.upsert_pending(
        page_id, "scan", [{"code": "invalid", "detail": "bad"}]
    )
    vectorizer = AsyncMock()
    vectorizer.delete_page_from_index.side_effect = RuntimeError("unavailable")
    await repair_service.delete_page(page_id)
    deletion_worker = DeletionWorker(
        repair_service.cleanup_repo, repair_service.file_repo, vectorizer
    )
    assert await deletion_worker.run_next()
    assert await repair_service.page_repo.get_page(page_id) is not None
    vectorizer.delete_page_from_index.side_effect = None
    assert await deletion_worker.run_next()
    assert await repair_service.page_repo.get_page(page_id) is None
