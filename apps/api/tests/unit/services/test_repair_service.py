"""Tests for repair detection and management."""

import asyncio
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from grimoire_api.config import settings
from grimoire_api.models.database import (
    PageStatus,
    RepairStatus,
)
from grimoire_api.repositories.database import DatabaseConnection
from grimoire_api.repositories.file_repository import FileRepository
from grimoire_api.repositories.job_repository import JobRepository
from grimoire_api.repositories.log_repository import LogRepository
from grimoire_api.repositories.page_repository import PageRepository
from grimoire_api.repositories.repair_repository import RepairRepository
from grimoire_api.services.repair_service import RepairService
from grimoire_api.utils.exceptions import DuplicateUrlError


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
    repair_service: RepairService,
    monkeypatch: pytest.MonkeyPatch,
    set_page_status,
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
        await set_page_status(repair_service.page_repo, page_id, PageStatus.SUCCEEDED)
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

    await repair_service.page_repo.db.execute(
        "UPDATE pages SET status='failed' WHERE id=?", (page_id,)
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

    await repair_service.page_repo.db.execute(
        "UPDATE pages SET status='failed' WHERE id=?", (page_id,)
    )

    with pytest.raises(FileExistsError):
        await repair_service.update_url(
            page_id, "https://example.com/one", "https://example.com/two"
        )


async def test_repository_preserves_database_error_for_duplicate(
    repair_service: RepairService,
) -> None:
    first = await repair_service.page_repo.create_page("https://a.example", "a")
    await repair_service.page_repo.create_page("https://b.example", "b")
    await repair_service.page_repo.db.execute(
        "UPDATE pages SET status='failed' WHERE id=?", (first,)
    )

    with pytest.raises(DuplicateUrlError):
        await repair_service.page_repo.update_url_if_current(
            first, "https://a.example", "https://b.example"
        )


@pytest.mark.parametrize(
    ("page_status", "job_status"),
    [
        (page_status, job_status)
        for page_status in ("queued", "processing", "deleting", "failed")
        for job_status in (None, "queued", "running")
        if page_status != "failed" or job_status is not None
    ],
)
async def test_update_url_rejects_busy_page_without_side_effects(
    repair_service: RepairService, page_status: str, job_status: str | None
) -> None:
    from grimoire_api.utils.exceptions import PageUrlUpdateConflictError

    repo = repair_service.page_repo
    page_id = await repo.create_page("https://example.com/old", "title")
    if job_status:
        await repo.db.execute(
            "INSERT INTO jobs (page_id, kind, status, start_step, created_at) "
            "VALUES (?, 'reprocess', ?, 'download', '2026-01-01T00:00:00+00:00')",
            (page_id, job_status),
        )
    await repo.db.execute(
        "UPDATE pages SET status=? WHERE id=?", (page_status, page_id)
    )
    before = await repo.get_page(page_id)
    logs = await repo.db.fetch_all("SELECT * FROM process_logs")
    repairs = await repo.db.fetch_all("SELECT * FROM repair_cases")
    with pytest.raises(PageUrlUpdateConflictError):
        await repair_service.update_url(
            page_id, "https://example.com/old", "https://example.com/new"
        )
    assert await repo.get_page(page_id) == before
    assert await repo.db.fetch_all("SELECT * FROM process_logs") == logs
    assert await repo.db.fetch_all("SELECT * FROM repair_cases") == repairs


@pytest.mark.parametrize("enqueue_first", [True, False])
async def test_url_update_serializes_with_enqueue(
    repair_service: RepairService, monkeypatch: pytest.MonkeyPatch, enqueue_first: bool
) -> None:
    import aiosqlite
    from grimoire_api.models.database import JobKind, PipelineStartStep
    from grimoire_api.utils.exceptions import PageUrlUpdateConflictError

    repo = repair_service.page_repo
    page_id = await repo.create_page("https://example.com/old", "title")
    await repo.db.execute("UPDATE pages SET status='failed' WHERE id=?", (page_id,))
    first_ready = asyncio.Event()
    second_started = asyncio.Event()
    original_commit = aiosqlite.Connection.commit
    original_execute = aiosqlite.Connection.execute
    first_task = None

    async def commit(conn):
        if asyncio.current_task() is first_task:
            first_ready.set()
            await asyncio.wait_for(second_started.wait(), timeout=5)
        return await original_commit(conn)

    def execute(conn, sql, parameters=None):
        if sql == "BEGIN IMMEDIATE" and asyncio.current_task() is not first_task:
            second_started.set()
        return original_execute(conn, sql, parameters)

    monkeypatch.setattr(aiosqlite.Connection, "commit", commit)
    monkeypatch.setattr(aiosqlite.Connection, "execute", execute)

    async def enqueue():
        return await JobRepository(repo.db).enqueue(
            page_id, JobKind.REPROCESS, PipelineStartStep.DOWNLOAD
        )

    async def update():
        return await repo.update_url_if_current(
            page_id, "https://example.com/old", "https://example.com/new"
        )

    first_task = asyncio.create_task(enqueue() if enqueue_first else update())
    await asyncio.wait_for(first_ready.wait(), timeout=5)
    second_task = asyncio.create_task(update() if enqueue_first else enqueue())
    results = await asyncio.wait_for(
        asyncio.gather(first_task, second_task, return_exceptions=True), timeout=10
    )
    assert not isinstance(results[0], BaseException)
    if enqueue_first:
        assert isinstance(results[1], PageUrlUpdateConflictError)
    else:
        assert not isinstance(results[1], BaseException)
    page = await repo.get_page(page_id)
    assert page and page.status == PageStatus.QUEUED
    assert page.url == (
        "https://example.com/old" if enqueue_first else "https://example.com/new"
    )
