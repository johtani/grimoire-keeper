"""Detection and management of pages requiring repair."""

import json
import re
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..config import settings
from ..models.database import PageStatus, RepairStatus
from ..models.external import FetchedDocument
from ..repositories.file_repository import FileRepository
from ..repositories.job_repository import JobRepository
from ..repositories.log_repository import LogRepository
from ..repositories.page_repository import PageRepository
from ..repositories.repair_repository import RepairRepository
from ..utils.exceptions import DatabaseError, FileOperationError, GrimoireAPIError


def validate_stored_source(
    page_id: int, url: str, source: dict[str, Any] | None, error: str | None = None
) -> list[dict[str, str]]:
    """保存済みJinaレスポンスとURLを検証する."""
    reasons: list[dict[str, str]] = []
    if re.search(r"(?:>|%3e)$", url.rstrip(), re.IGNORECASE):
        reasons.append(
            {"code": "malformed_url_suffix", "detail": "URL ends with > or %3E"}
        )
    if error:
        reasons.append({"code": error, "detail": f"page {page_id} JSON is {error}"})
        return reasons
    if source is None:
        return reasons
    data = source.get("data") if isinstance(source, dict) else None
    if not isinstance(data, dict):
        reasons.append({"code": "invalid_jina_data", "detail": "data is not an object"})
        return reasons
    for name, value in (
        ("code", source.get("code")),
        ("data.httpStatus", data.get("httpStatus")),
    ):
        if isinstance(value, int) and not isinstance(value, bool) and value >= 400:
            reasons.append({"code": "jina_http_error", "detail": f"{name}={value}"})
    try:
        FetchedDocument.from_jina_response(source, source_url=url)
    except (ValidationError, ValueError, TypeError) as exc:
        if not any(reason["code"] == "jina_http_error" for reason in reasons):
            reasons.append({"code": "invalid_jina_data", "detail": str(exc)})
    return reasons


class RepairService:
    """修復ケースの検出、取込、URL更新を調整する."""

    def __init__(
        self,
        page_repo: PageRepository,
        repair_repo: RepairRepository,
        file_repo: FileRepository,
        log_repo: LogRepository,
        job_repo: JobRepository,
        report_path: str | None = None,
    ):
        self.page_repo = page_repo
        self.repair_repo = repair_repo
        self.file_repo = file_repo
        self.log_repo = log_repo
        self.job_repo = job_repo
        self.report_path = Path(report_path or settings.REPAIR_REPORT_PATH)

    async def _validate_page(self, page_id: int, url: str) -> list[dict[str, str]]:
        try:
            source = await self.file_repo.load_json_file(page_id)
        except FileOperationError as exc:
            code = (
                "missing_json"
                if not await self.file_repo.file_exists(page_id)
                else "invalid_json"
            )
            return validate_stored_source(page_id, url, None, code) + (
                []
                if code == "missing_json"
                else [{"code": "invalid_json_detail", "detail": str(exc)}]
            )
        return validate_stored_source(page_id, url, source)

    async def scan(self) -> dict[str, int]:
        pages = await self.page_repo.get_all_pages(limit=100000)
        detected = 0
        for page in pages:
            if page.id is None:
                continue
            reasons = await self._validate_page(page.id, page.url)
            if reasons:
                await self.repair_repo.upsert_pending(page.id, "scan", reasons)
                detected += 1
        return {"scanned": len(pages), "pending": detected, "resolved": 0}

    async def import_report(self) -> dict[str, int]:
        try:
            document = json.loads(self.report_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise FileOperationError(
                f"Repair report not found: {self.report_path}"
            ) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise FileOperationError(f"Invalid repair report: {exc}") from exc
        pending = document.get("repair_pending") if isinstance(document, dict) else None
        if document.get("schema_version") != 1 or not isinstance(pending, list):
            raise GrimoireAPIError("Unsupported repair report schema")
        if document.get("repair_pending_count") != len(pending):
            raise GrimoireAPIError("repair_pending_count does not match entries")
        imported = missing = mismatched = 0
        seen: set[int] = set()
        for item in pending:
            if not isinstance(item, dict) or not isinstance(item.get("page_id"), int):
                raise GrimoireAPIError("Invalid repair report entry")
            page_id = item["page_id"]
            if page_id in seen:
                raise GrimoireAPIError("Duplicate page_id in repair report")
            seen.add(page_id)
            page = await self.page_repo.get_page(page_id)
            if page is None:
                missing += 1
                continue
            reasons = item.get("reasons")
            if not isinstance(reasons, list) or not all(
                isinstance(reason, dict)
                and isinstance(reason.get("code"), str)
                and isinstance(reason.get("detail"), str)
                for reason in reasons
            ):
                raise GrimoireAPIError("Invalid repair reasons")
            report_url = item.get("url")
            if report_url != page.url:
                reasons = [
                    *reasons,
                    {
                        "code": "report_url_mismatch",
                        "detail": f"report={report_url}; current={page.url}",
                    },
                ]
                mismatched += 1
            await self.repair_repo.upsert_pending(
                page_id,
                "migration",
                reasons,
                report_url,
                reopen_resolved=False,
            )
            imported += 1
        return {
            "imported": imported,
            "missing_pages": missing,
            "url_mismatches": mismatched,
        }

    async def list_cases(self, status: RepairStatus | None) -> list[dict[str, Any]]:
        cases = await self.repair_repo.list_cases(status)
        pages = await self.page_repo.get_pages_by_ids([case.page_id for case in cases])
        return [
            {
                "page_id": case.page_id,
                "url": pages[case.page_id].url if case.page_id in pages else None,
                "report_url": case.report_url,
                "source": case.source,
                "reasons": case.reasons,
                "repair_status": case.status.value,
                "detected_at": case.detected_at,
                "resolved_at": case.resolved_at,
            }
            for case in cases
        ]

    async def get_detail(self, page_id: int) -> dict[str, Any]:
        page = await self.page_repo.get_page(page_id)
        if page is None:
            raise LookupError("Page not found")
        case = await self.repair_repo.get_by_page_id(page_id)
        reasons = await self._validate_page(page_id, page.url)
        job = await self.job_repo.get_latest_for_page(page_id)
        return {
            "page_id": page_id,
            "url": page.url,
            "repair_status": case.status.value if case else None,
            "reasons": case.reasons if case else reasons,
            "json_validation": {"valid": not reasons, "reasons": reasons},
            "latest_error": await self.log_repo.get_latest_error(page_id),
            "latest_job": (
                {
                    "id": job.id,
                    "status": job.status.value,
                    "start_step": job.start_step.value,
                    "current_step": job.current_step.value
                    if job.current_step
                    else None,
                    "error_message": job.error_message,
                }
                if job
                else None
            ),
        }

    async def update_url(
        self, page_id: int, current_url: str, new_url: str
    ) -> dict[str, str]:
        page = await self.page_repo.get_page(page_id)
        if page is None:
            raise LookupError("Page not found")
        try:
            updated = await self.page_repo.update_url_if_current(
                page_id, current_url, new_url
            )
        except DatabaseError as exc:
            if "already belongs" in str(exc):
                raise FileExistsError("URL already exists") from exc
            raise
        if not updated:
            raise RuntimeError("Current URL does not match")
        reasons = [
            {
                "code": "url_changed",
                "detail": (
                    f"URL changed from {current_url} to {new_url}; "
                    "reprocessing required"
                ),
            }
        ]
        await self.repair_repo.upsert_pending(page_id, "manual", reasons, current_url)
        log_id = await self.log_repo.create_log(current_url, "url_updated", page_id)
        await self.log_repo.update_status(log_id, "url_updated", f"new_url={new_url}")
        return {
            "current_url": current_url,
            "new_url": new_url,
            "status": PageStatus.FAILED.value,
        }
