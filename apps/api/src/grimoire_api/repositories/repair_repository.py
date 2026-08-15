"""Repair-case persistence."""

import json
from datetime import datetime

import aiosqlite

from ..models.database import RepairCase, RepairStatus
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
        now = datetime.now()
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
            (datetime.now(), page_id),
        )

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
                detected_at=datetime.fromisoformat(row["detected_at"]),
                resolved_at=(
                    datetime.fromisoformat(row["resolved_at"])
                    if row["resolved_at"]
                    else None
                ),
            )
        except Exception as exc:
            raise DatabaseError(f"Invalid repair case: {exc}") from exc
