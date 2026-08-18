"""Tests for repair detection and management."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from grimoire_api.models.database import (
    JobKind,
    PipelineStartStep,
    RepairStatus,
)
from grimoire_api.repositories.database import DatabaseConnection
from grimoire_api.repositories.file_repository import FileRepository
from grimoire_api.repositories.job_repository import JobRepository
from grimoire_api.repositories.log_repository import LogRepository
from grimoire_api.repositories.page_repository import PageRepository
from grimoire_api.repositories.repair_repository import RepairRepository
from grimoire_api.services.repair_service import RepairService
from grimoire_api.utils.exceptions import (
    DatabaseError,
    RepairDeletionConflictError,
    RepairDeletionError,
    VectorizerError,
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
    with pytest.raises(DatabaseError, match="already belongs"):
        await repair_service.page_repo.update_url_if_current(
            first, "https://a.example", "https://b.example"
        )


async def test_delete_pending_repair_page_removes_all_data(
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
        "status": "deleted",
    }
    vectorizer.delete_page_from_index.assert_awaited_once_with(page_id)
    assert not await repair_service.file_repo.file_exists(page_id)
    assert await repair_service.page_repo.get_page(page_id) is None
    assert await repair_service.repair_repo.get_by_page_id(page_id) is None


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
    repair_service.vectorizer = AsyncMock()

    with pytest.raises(RepairDeletionConflictError, match="queued or running"):
        await repair_service.delete_page(page_id)
    repair_service.vectorizer.delete_page_from_index.assert_not_awaited()


async def test_delete_failure_is_logged_and_can_be_retried(
    repair_service: RepairService,
) -> None:
    page_id = await repair_service.page_repo.create_page(
        "https://example.com/retry-delete", "retry"
    )
    await repair_service.repair_repo.upsert_pending(
        page_id, "scan", [{"code": "invalid", "detail": "bad"}]
    )
    vectorizer = AsyncMock()
    vectorizer.delete_page_from_index.side_effect = VectorizerError("unavailable")
    repair_service.vectorizer = vectorizer

    with pytest.raises(RepairDeletionError, match="can be retried"):
        await repair_service.delete_page(page_id)

    assert await repair_service.page_repo.get_page(page_id) is not None
    assert "unavailable" in (
        await repair_service.log_repo.get_latest_error(page_id) or ""
    )
    vectorizer.delete_page_from_index.side_effect = None
    await repair_service.delete_page(page_id)
    assert await repair_service.page_repo.get_page(page_id) is None
