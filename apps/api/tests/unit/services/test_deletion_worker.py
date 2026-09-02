"""Failure-injection tests for deletion saga execution."""

from unittest.mock import AsyncMock

from grimoire_api.repositories.cleanup_job_repository import CleanupJobRepository
from grimoire_api.repositories.repair_repository import RepairRepository
from grimoire_api.services.deletion_worker import DeletionWorker


async def test_file_failure_is_persisted_and_retry_completes(
    temp_db, page_repo, file_repo
) -> None:
    page_id = await page_repo.create_page("https://delete.example", "delete")
    await RepairRepository(temp_db).upsert_pending(
        page_id, "scan", [{"code": "invalid", "detail": "bad"}]
    )
    await file_repo.save_json_file(page_id, {"data": {}})
    cleanup_repo = CleanupJobRepository(temp_db)
    await cleanup_repo.enqueue(page_id)
    vectorizer = AsyncMock()
    original_delete = file_repo.delete_json_file
    file_repo.delete_json_file = AsyncMock(side_effect=OSError("disk unavailable"))
    worker = DeletionWorker(cleanup_repo, file_repo, vectorizer)

    assert await worker.run_next()
    row = await temp_db.fetch_one(
        "SELECT status, error_message FROM cleanup_jobs WHERE page_id=?", (page_id,)
    )
    assert row is not None and row["status"] == "queued"
    assert "disk unavailable" in row["error_message"]

    file_repo.delete_json_file = original_delete
    assert await worker.run_next()
    assert await page_repo.get_page(page_id) is None


async def test_finalize_failure_retries_external_deletes_safely(
    temp_db, page_repo, file_repo
) -> None:
    page_id = await page_repo.create_page("https://finalize.example", "delete")
    await RepairRepository(temp_db).upsert_pending(
        page_id, "scan", [{"code": "invalid", "detail": "bad"}]
    )
    cleanup_repo = CleanupJobRepository(temp_db)
    await cleanup_repo.enqueue(page_id)
    vectorizer = AsyncMock()
    worker = DeletionWorker(cleanup_repo, file_repo, vectorizer)
    await temp_db.execute(
        "CREATE TRIGGER reject_page_finalize BEFORE DELETE ON pages "
        "BEGIN SELECT RAISE(ABORT, 'finalize unavailable'); END"
    )

    assert await worker.run_next()
    assert await page_repo.get_page(page_id) is not None
    await temp_db.execute("DROP TRIGGER reject_page_finalize")

    assert await worker.run_next()
    assert await page_repo.get_page(page_id) is None
    assert vectorizer.delete_page_from_index.await_count == 2
