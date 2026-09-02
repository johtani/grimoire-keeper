"""Persistent cleanup jobs for the page-deletion saga."""

import aiosqlite

from ..models.database import CleanupJob, CleanupJobStatus
from ..utils.datetime import as_utc, utc_now_isoformat
from ..utils.exceptions import DatabaseError, RepairDeletionConflictError
from .database import DatabaseConnection


class CleanupJobRepository:
    """削除受付、claim、再試行、最終確定を管理する."""

    def __init__(self, db: DatabaseConnection | None = None):
        self.db = db or DatabaseConnection()

    async def enqueue(self, page_id: int) -> CleanupJob:
        """検証と deleting 遷移と job 登録を短いトランザクションで行う."""
        try:
            async with self.db.connect() as conn:
                conn.row_factory = aiosqlite.Row
                await conn.execute("BEGIN IMMEDIATE")
                page = await (
                    await conn.execute(
                        "SELECT status FROM pages WHERE id=?", (page_id,)
                    )
                ).fetchone()
                if page is None:
                    await conn.rollback()
                    raise LookupError("Page not found")
                existing = await (
                    await conn.execute(
                        "SELECT * FROM cleanup_jobs WHERE page_id=?", (page_id,)
                    )
                ).fetchone()
                if page["status"] == "deleting" and existing is not None:
                    await conn.commit()
                    return self._row_to_job(existing)
                repair = await (
                    await conn.execute(
                        "SELECT status FROM repair_cases WHERE page_id=?", (page_id,)
                    )
                ).fetchone()
                if repair is None or repair["status"] != "pending":
                    await conn.rollback()
                    raise RepairDeletionConflictError(
                        "Only pages with a pending repair case can be deleted"
                    )
                active = await (
                    await conn.execute(
                        "SELECT 1 FROM jobs WHERE page_id=? "
                        "AND status IN ('queued', 'running') LIMIT 1",
                        (page_id,),
                    )
                ).fetchone()
                if active is not None:
                    await conn.rollback()
                    raise RepairDeletionConflictError(
                        "Page has a queued or running job"
                    )
                now = utc_now_isoformat()
                await conn.execute(
                    "UPDATE pages SET status='deleting', updated_at=? WHERE id=?",
                    (now, page_id),
                )
                await conn.execute(
                    """INSERT INTO cleanup_jobs
                    (page_id, status, attempt, created_at, updated_at)
                    VALUES (?, 'queued', 0, ?, ?)
                    ON CONFLICT(page_id) DO UPDATE SET
                        status='queued', error_message=NULL,
                        updated_at=excluded.updated_at""",
                    (page_id, now, now),
                )
                row = await (
                    await conn.execute(
                        "SELECT * FROM cleanup_jobs WHERE page_id=?", (page_id,)
                    )
                ).fetchone()
                await conn.commit()
                if row is None:
                    raise RuntimeError("Cleanup job was not created")
                return self._row_to_job(row)
        except (LookupError, RepairDeletionConflictError):
            raise
        except Exception as exc:
            raise DatabaseError(f"Failed to enqueue cleanup job: {exc}") from exc

    async def claim_next(self) -> CleanupJob | None:
        """最古の queued job を原子的に claim する."""
        try:
            async with self.db.connect() as conn:
                conn.row_factory = aiosqlite.Row
                await conn.execute("BEGIN IMMEDIATE")
                row = await (
                    await conn.execute(
                        "SELECT * FROM cleanup_jobs WHERE status='queued' "
                        "ORDER BY updated_at, id LIMIT 1"
                    )
                ).fetchone()
                if row is None:
                    await conn.commit()
                    return None
                now = utc_now_isoformat()
                await conn.execute(
                    "UPDATE cleanup_jobs SET status='running', attempt=attempt+1, "
                    "error_message=NULL, updated_at=? WHERE id=?",
                    (now, row["id"]),
                )
                await conn.commit()
                values = dict(row)
                values.update(
                    status="running", attempt=row["attempt"] + 1, updated_at=now
                )
                return self._row_to_job(values)
        except Exception as exc:
            raise DatabaseError(f"Failed to claim cleanup job: {exc}") from exc

    async def retry(self, job_id: int, message: str) -> None:
        await self.db.execute(
            "UPDATE cleanup_jobs SET status='queued', error_message=?, updated_at=? "
            "WHERE id=? AND status='running'",
            (message, utc_now_isoformat(), job_id),
        )

    async def recover_running(self) -> None:
        await self.db.execute(
            "UPDATE cleanup_jobs SET status='queued', "
            "error_message='worker interrupted', updated_at=? WHERE status='running'",
            (utc_now_isoformat(),),
        )

    async def finalize(self, job: CleanupJob) -> None:
        """外部 cleanup 後に SQLite データを原子的に削除する."""
        try:
            async with self.db.connect() as conn:
                await conn.execute("BEGIN IMMEDIATE")
                current = await (
                    await conn.execute(
                        "SELECT status FROM cleanup_jobs WHERE id=? AND page_id=?",
                        (job.id, job.page_id),
                    )
                ).fetchone()
                if current is None:
                    await conn.commit()
                    return
                if current[0] != "running":
                    raise RuntimeError("Cleanup job is not running")
                for table in ("process_logs", "jobs", "repair_cases", "cleanup_jobs"):
                    await conn.execute(
                        f"DELETE FROM {table} WHERE page_id=?", (job.page_id,)
                    )
                await conn.execute("DELETE FROM pages WHERE id=?", (job.page_id,))
                await conn.commit()
        except Exception as exc:
            raise DatabaseError(f"Failed to finalize cleanup job: {exc}") from exc

    @staticmethod
    def _row_to_job(row: aiosqlite.Row | dict) -> CleanupJob:
        return CleanupJob(
            id=int(row["id"]),
            page_id=int(row["page_id"]),
            status=CleanupJobStatus(row["status"]),
            attempt=int(row["attempt"]),
            error_message=row["error_message"],
            created_at=as_utc(row["created_at"]),
            updated_at=as_utc(row["updated_at"]),
        )
