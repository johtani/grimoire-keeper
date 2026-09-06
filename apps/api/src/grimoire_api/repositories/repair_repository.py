"""Repair-case persistence."""

import json

import aiosqlite

from ..models.database import RepairCase, RepairStatus
from ..utils.datetime import as_utc, utc_now_isoformat
from ..utils.exceptions import DatabaseError
from .database import DatabaseConnection


class RepairRepository:
    """修復ケースの登録・解消を管理する."""

    def __init__(self, db: DatabaseConnection | None = None):
        self.db = db or DatabaseConnection()

    async def upsert_pending(
        self,
        page_id: int,
        source: str,
        reasons: list[dict[str, str]],
        report_url: str | None = None,
        *,
        reopen_resolved: bool = True,
    ) -> None:
        now = utc_now_isoformat()
        await self.db.execute(
            """INSERT INTO repair_cases
            (page_id, source, report_url, reasons, status, detected_at, resolved_at)
            VALUES (?, ?, ?, ?, 'pending', ?, NULL)
            ON CONFLICT(page_id) DO UPDATE SET
                source=excluded.source, report_url=excluded.report_url,
                reasons=excluded.reasons,
                status=CASE
                    WHEN repair_cases.status='resolved' AND ?=0 THEN 'resolved'
                    ELSE 'pending' END,
                detected_at=CASE
                    WHEN repair_cases.status='resolved' AND ?=0
                    THEN repair_cases.detected_at ELSE excluded.detected_at END,
                resolved_at=CASE
                    WHEN repair_cases.status='resolved' AND ?=0
                    THEN repair_cases.resolved_at ELSE NULL END""",
            (
                page_id,
                source,
                report_url,
                json.dumps(reasons),
                now,
                reopen_resolved,
                reopen_resolved,
                reopen_resolved,
            ),
        )

    async def resolve(self, page_id: int) -> None:
        await self.db.execute(
            """UPDATE repair_cases SET status='resolved', resolved_at=?
            WHERE page_id=? AND status='pending'""",
            (utc_now_isoformat(), page_id),
        )

    async def begin_or_resume_scan(self, upper_bound: int) -> dict[str, int]:
        """新しいscanを開始するか、永続checkpointを読み出す."""
        try:
            async with self.db.connect() as conn:
                conn.row_factory = aiosqlite.Row
                await conn.execute("BEGIN IMMEDIATE")
                row = await (
                    await conn.execute("SELECT * FROM repair_scan_state WHERE id=1")
                ).fetchone()
                if row is None:
                    raise DatabaseError("Repair scan checkpoint is missing")
                if row["upper_bound"] is None:
                    now = utc_now_isoformat()
                    await conn.execute(
                        """UPDATE repair_scan_state
                        SET upper_bound=?, cursor=0, scanned=0, pending=0,
                            resolved=0, started_at=?, updated_at=?
                        WHERE id=1""",
                        (upper_bound, now, now),
                    )
                    row = await (
                        await conn.execute("SELECT * FROM repair_scan_state WHERE id=1")
                    ).fetchone()
                if row is None:
                    raise DatabaseError("Repair scan checkpoint is missing")
                await conn.commit()
                return self._scan_state(row)
        except DatabaseError:
            raise
        except Exception as exc:
            raise DatabaseError(f"Failed to begin repair scan: {exc}") from exc

    async def record_scan_result(
        self, page_id: int, reasons: list[dict[str, str]]
    ) -> None:
        """repair case更新とscan checkpoint前進を同一transactionで行う."""
        try:
            async with self.db.connect() as conn:
                await conn.execute("BEGIN IMMEDIATE")
                resolved = 0
                if reasons:
                    now = utc_now_isoformat()
                    await conn.execute(
                        """INSERT INTO repair_cases
                        (page_id, source, report_url, reasons, status,
                         detected_at, resolved_at)
                        VALUES (?, 'scan', NULL, ?, 'pending', ?, NULL)
                        ON CONFLICT(page_id) DO UPDATE SET
                            source='scan', report_url=NULL, reasons=excluded.reasons,
                            status='pending',
                            detected_at=CASE
                                WHEN repair_cases.status='pending'
                                THEN repair_cases.detected_at
                                ELSE excluded.detected_at END,
                            resolved_at=NULL""",
                        (page_id, json.dumps(reasons), now),
                    )
                else:
                    cursor = await conn.execute(
                        """UPDATE repair_cases SET status='resolved', resolved_at=?
                        WHERE page_id=? AND status='pending'""",
                        (utc_now_isoformat(), page_id),
                    )
                    resolved = int(cursor.rowcount == 1)
                checkpoint = await conn.execute(
                    """UPDATE repair_scan_state
                    SET cursor=?, scanned=scanned+1, pending=pending+?,
                        resolved=resolved+?, updated_at=?
                    WHERE id=1 AND upper_bound IS NOT NULL AND cursor < ?""",
                    (
                        page_id,
                        int(bool(reasons)),
                        resolved,
                        utc_now_isoformat(),
                        page_id,
                    ),
                )
                if checkpoint.rowcount != 1:
                    raise DatabaseError(
                        f"Repair scan checkpoint did not advance to page {page_id}"
                    )
                await conn.commit()
        except Exception as exc:
            raise DatabaseError(f"Failed to record repair scan result: {exc}") from exc

    async def complete_scan(self) -> dict[str, int]:
        """累積結果を返し、次回scan用にcheckpointを初期化する."""
        try:
            async with self.db.connect() as conn:
                conn.row_factory = aiosqlite.Row
                await conn.execute("BEGIN IMMEDIATE")
                row = await (
                    await conn.execute("SELECT * FROM repair_scan_state WHERE id=1")
                ).fetchone()
                if row is None or row["upper_bound"] is None:
                    raise DatabaseError("No repair scan is active")
                result = {
                    "scanned": int(row["scanned"]),
                    "pending": int(row["pending"]),
                    "resolved": int(row["resolved"]),
                }
                await conn.execute(
                    """UPDATE repair_scan_state
                    SET upper_bound=NULL, cursor=0, scanned=0, pending=0,
                        resolved=0, started_at=NULL, updated_at=? WHERE id=1""",
                    (utc_now_isoformat(),),
                )
                await conn.commit()
                return result
        except DatabaseError:
            raise
        except Exception as exc:
            raise DatabaseError(f"Failed to complete repair scan: {exc}") from exc

    @staticmethod
    def _scan_state(row: aiosqlite.Row) -> dict[str, int]:
        return {
            "upper_bound": int(row["upper_bound"]),
            "cursor": int(row["cursor"]),
            "scanned": int(row["scanned"]),
            "pending": int(row["pending"]),
            "resolved": int(row["resolved"]),
        }

    async def get_by_page_id(self, page_id: int) -> RepairCase | None:
        row = await self.db.fetch_one(
            "SELECT * FROM repair_cases WHERE page_id=?", (page_id,)
        )
        return self._row_to_case(row) if row else None

    async def list_cases(self, status: RepairStatus | None = None) -> list[RepairCase]:
        query = "SELECT * FROM repair_cases"
        params: tuple = ()
        if status is not None:
            query += " WHERE status=?"
            params = (status.value,)
        query += " ORDER BY detected_at DESC, id DESC"
        rows = await self.db.fetch_all(query, params)
        return [self._row_to_case(row) for row in rows]

    @staticmethod
    def _row_to_case(row: aiosqlite.Row) -> RepairCase:
        try:
            reasons = json.loads(row["reasons"])
            return RepairCase(
                id=int(row["id"]),
                page_id=int(row["page_id"]),
                source=str(row["source"]),
                report_url=row["report_url"],
                reasons=reasons,
                status=RepairStatus(row["status"]),
                detected_at=as_utc(row["detected_at"]),
                resolved_at=(
                    as_utc(row["resolved_at"]) if row["resolved_at"] else None
                ),
            )
        except Exception as exc:
            raise DatabaseError(f"Invalid repair case: {exc}") from exc
