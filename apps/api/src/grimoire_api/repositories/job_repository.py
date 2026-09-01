"""Persistent processing job repository."""

from datetime import datetime

import aiosqlite

from ..models.database import Job, JobKind, JobStatus, PipelineStartStep, ProcessingStep
from ..utils.datetime import as_utc, utc_isoformat, utc_now, utc_now_isoformat
from ..utils.exceptions import DatabaseError
from .database import DatabaseConnection


class JobRepository:
    """永続ジョブの登録と状態遷移を管理する."""

    def __init__(self, db: DatabaseConnection | None = None):
        self.db = db or DatabaseConnection()

    async def enqueue(
        self, page_id: int, kind: JobKind, start_step: PipelineStartStep
    ) -> int:
        """ジョブ登録とページ状態更新を同一トランザクションで行う."""
        try:
            async with self.db.connect() as conn:
                await conn.execute("BEGIN IMMEDIATE")
                cursor = await conn.execute(
                    """INSERT INTO jobs
                    (page_id, kind, status, start_step, created_at)
                    VALUES (?, ?, 'queued', ?, ?)""",
                    (page_id, kind.value, start_step.value, utc_now_isoformat()),
                )
                job_id = int(cursor.lastrowid or 0)
                await conn.execute(
                    """INSERT INTO process_logs
                    (page_id, job_id, attempt, url, status, created_at)
                    SELECT id, ?, 0, url, 'job_queued', ? FROM pages WHERE id=?""",
                    (job_id, utc_now_isoformat(), page_id),
                )
                await conn.execute(
                    "UPDATE pages SET status='queued', updated_at=? WHERE id=?",
                    (utc_now_isoformat(), page_id),
                )
                await conn.commit()
                return job_id
        except Exception as e:
            raise DatabaseError(f"Failed to enqueue job: {e}")

    async def claim_next(self) -> Job | None:
        """最古の queued ジョブを原子的に取得して running にする."""
        try:
            async with self.db.connect() as conn:
                conn.row_factory = aiosqlite.Row
                await conn.execute("BEGIN IMMEDIATE")
                row = await (
                    await conn.execute(
                        """SELECT * FROM jobs WHERE status='queued'
                        ORDER BY created_at, id LIMIT 1"""
                    )
                ).fetchone()
                if row is None:
                    await conn.commit()
                    return None
                now = utc_now()
                stored_now = utc_isoformat(now)
                await conn.execute(
                    """UPDATE jobs SET status='running', attempt=attempt+1,
                    started_at=?, finished_at=NULL, error_message=NULL WHERE id=?""",
                    (stored_now, row["id"]),
                )
                await conn.execute(
                    "UPDATE pages SET status='processing', updated_at=? WHERE id=?",
                    (stored_now, row["page_id"]),
                )
                await conn.execute(
                    """INSERT INTO process_logs
                    (page_id, job_id, attempt, url, status, created_at)
                    SELECT id, ?, ?, url, 'job_claimed', ? FROM pages WHERE id=?""",
                    (row["id"], row["attempt"] + 1, stored_now, row["page_id"]),
                )
                await conn.commit()
                values = dict(row)
                values.update(
                    status="running", attempt=row["attempt"] + 1, started_at=now
                )
                return self._row_to_job(values)
        except Exception as e:
            raise DatabaseError(f"Failed to claim job: {e}")

    async def update_step(self, job_id: int, step: ProcessingStep) -> None:
        now = utc_now_isoformat()
        event = {
            ProcessingStep.DOWNLOADED: "download_completed",
            ProcessingStep.LLM_PROCESSED: "llm_completed",
            ProcessingStep.VECTORIZED: "vectorize_completed",
            ProcessingStep.COMPLETED: "pipeline_completed",
        }[step]
        await self.db.execute_transaction(
            [
                (
                    "UPDATE jobs SET current_step=? WHERE id=?",
                    (step.value, job_id),
                ),
                (
                    """INSERT INTO process_logs
                    (page_id, job_id, attempt, url, status, created_at)
                    SELECT j.page_id, j.id, j.attempt, p.url, ?, ?
                    FROM jobs j JOIN pages p ON p.id=j.page_id WHERE j.id=?""",
                    (event, now, job_id),
                ),
            ]
        )

    async def succeed(self, job_id: int, page_id: int) -> bool:
        """実行中ジョブを成功に遷移し、初回の終端更新かを返す."""
        return await self._finish(job_id, page_id, "succeeded")

    async def fail(self, job_id: int, page_id: int, message: str) -> bool:
        """実行中ジョブを失敗に遷移し、初回の終端更新かを返す."""
        return await self._finish(job_id, page_id, "failed", message)

    async def _finish(
        self,
        job_id: int,
        page_id: int,
        status: str,
        message: str | None = None,
    ) -> bool:
        """終端状態、ページ状態、イベントを一度だけ原子的に更新する."""
        now = utc_now_isoformat()
        try:
            async with self.db.connect() as conn:
                await conn.execute("BEGIN IMMEDIATE")
                cursor = await conn.execute(
                    """UPDATE jobs SET status=?, error_message=?, finished_at=?
                    WHERE id=? AND page_id=? AND status='running'""",
                    (status, message, now, job_id, page_id),
                )
                if cursor.rowcount == 0:
                    await conn.commit()
                    return False
                await conn.execute(
                    "UPDATE pages SET status=?, updated_at=? WHERE id=?",
                    (status, now, page_id),
                )
                await conn.execute(
                    """INSERT INTO process_logs
                    (page_id, job_id, attempt, url, status, error_message, created_at)
                    SELECT j.page_id, j.id, j.attempt, p.url, ?, ?, ?
                    FROM jobs j JOIN pages p ON p.id=j.page_id WHERE j.id=?""",
                    (status, message, now, job_id),
                )
                await conn.commit()
                return True
        except Exception as e:
            raise DatabaseError(f"Failed to finish job: {e}")

    async def recover_running(self) -> list[Job]:
        """中断された attempt を返し、running ジョブを再実行可能にする."""
        try:
            async with self.db.connect() as conn:
                conn.row_factory = aiosqlite.Row
                await conn.execute("BEGIN IMMEDIATE")
                rows = await (
                    await conn.execute("SELECT * FROM jobs WHERE status='running'")
                ).fetchall()
                now = utc_now_isoformat()
                await conn.execute(
                    """INSERT INTO process_logs
                    (page_id, job_id, attempt, url, status, error_message, created_at)
                    SELECT j.page_id, j.id, j.attempt, p.url, 'interrupted',
                           'Worker restarted while attempt was running', ?
                    FROM jobs j JOIN pages p ON p.id=j.page_id
                    WHERE j.status='running'""",
                    (now,),
                )
                await conn.execute(
                    """UPDATE jobs SET status='queued', started_at=NULL
                    WHERE status='running'"""
                )
                await conn.execute(
                    """UPDATE pages SET status='queued' WHERE id IN
                    (SELECT page_id FROM jobs WHERE status='queued')"""
                )
                await conn.commit()
                return [self._row_to_job(row) for row in rows]
        except Exception as e:
            raise DatabaseError(f"Failed to recover jobs: {e}")

    async def get_latest_for_page(self, page_id: int) -> Job | None:
        row = await self.db.fetch_one(
            "SELECT * FROM jobs WHERE page_id=? "
            "ORDER BY created_at DESC, id DESC LIMIT 1",
            (page_id,),
        )
        return self._row_to_job(row) if row else None

    async def has_active_for_page(self, page_id: int) -> bool:
        """ページに queued または running ジョブがあるか確認する."""
        row = await self.db.fetch_one(
            "SELECT 1 FROM jobs WHERE page_id=? "
            "AND status IN ('queued', 'running') LIMIT 1",
            (page_id,),
        )
        return row is not None

    @staticmethod
    def _parse_datetime(value: str | datetime | None) -> datetime | None:
        return as_utc(value) if value is not None else None

    @classmethod
    def _row_to_job(cls, row: dict | aiosqlite.Row) -> Job:
        created_at = cls._parse_datetime(row["created_at"])
        if created_at is None:
            raise DatabaseError("Job created_at is missing")
        return Job(
            id=int(row["id"]),
            page_id=int(row["page_id"]),
            kind=JobKind(row["kind"]),
            status=JobStatus(row["status"]),
            current_step=(
                ProcessingStep(row["current_step"]) if row["current_step"] else None
            ),
            start_step=PipelineStartStep(row["start_step"]),
            attempt=int(row["attempt"]),
            error_message=row["error_message"],
            created_at=created_at,
            started_at=cls._parse_datetime(row["started_at"]),
            finished_at=cls._parse_datetime(row["finished_at"]),
        )
