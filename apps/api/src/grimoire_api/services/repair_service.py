"""Detection and management of pages requiring repair."""

import asyncio
import json
import re
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from weaviate.classes.query import Filter

from ..config import settings
from ..models.database import Page, PageStatus, RepairStatus
from ..models.external import FetchedDocument
from ..repositories.cleanup_job_repository import CleanupJobRepository
from ..repositories.file_repository import FileRepository
from ..repositories.job_repository import JobRepository
from ..repositories.log_repository import LogRepository
from ..repositories.page_repository import PageRepository
from ..repositories.repair_repository import RepairRepository
from ..utils.exceptions import (
    DatabaseError,
    DuplicateUrlError,
    FileOperationError,
    GrimoireAPIError,
)


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
        cleanup_repo: CleanupJobRepository | None = None,
        weaviate_client: Any | None = None,
    ):
        self.page_repo = page_repo
        self.repair_repo = repair_repo
        self.file_repo = file_repo
        self.log_repo = log_repo
        self.job_repo = job_repo
        self.cleanup_repo = cleanup_repo
        self.weaviate_client = weaviate_client
        self.report_path = Path(report_path or settings.REPAIR_REPORT_PATH)
        self._weaviate_semaphore = asyncio.Semaphore(
            settings.REPAIR_SCAN_WEAVIATE_CONCURRENCY
        )

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

    async def _is_page_registered(self, page_id: int) -> bool:
        client = self.weaviate_client
        if client is None:
            raise RuntimeError("Weaviate client is not configured")
        collection = client.collections.get(settings.WEAVIATE_PAGE_COLLECTION_NAME)
        async with self._weaviate_semaphore:
            async with asyncio.timeout(settings.REPAIR_SCAN_WEAVIATE_TIMEOUT):
                response = await asyncio.to_thread(
                    collection.query.fetch_objects,
                    filters=Filter.by_property("pageId").equal(page_id),
                    limit=1,
                )
        return bool(response.objects)

    async def _validate_scan_page(self, page: Page) -> list[dict[str, str]]:
        if page.id is None:
            return []
        reasons = await self._validate_page(page.id, page.url)
        if (
            self.weaviate_client is not None
            and page.status == PageStatus.SUCCEEDED
            and not await self._is_page_registered(page.id)
        ):
            reasons.append(
                {
                    "code": "missing_weaviate_page",
                    "detail": f"page {page.id} is not registered in Weaviate",
                }
            )
        return reasons

    async def scan(self) -> dict[str, int]:
        """固定snapshotをbounded batchで検査し、中断時は次回再開する."""
        upper_bound = await self.page_repo.get_max_page_id()
        state = await self.repair_repo.begin_or_resume_scan(upper_bound)
        while True:
            pages = await self.page_repo.get_pages_after_id(
                state["cursor"], state["upper_bound"], settings.REPAIR_SCAN_BATCH_SIZE
            )
            if not pages:
                return await self.repair_repo.complete_scan()

            results = await asyncio.gather(
                *(self._validate_scan_page(page) for page in pages)
            )
            for page, reasons in zip(pages, results, strict=True):
                if page.id is None:
                    continue
                await self.repair_repo.record_scan_result(page.id, reasons)
                state["cursor"] = page.id

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
        except DuplicateUrlError as exc:
            raise FileExistsError("URL already exists") from exc
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
        await self.log_repo.create_log(
            current_url,
            "url_updated",
            page_id,
            error_message=f"new_url={new_url}",
        )
        return {
            "current_url": current_url,
            "new_url": new_url,
            "status": PageStatus.FAILED.value,
        }

    async def delete_page(self, page_id: int) -> dict[str, Any]:
        """pending repair ページの非同期削除を受付する."""
        page = await self.page_repo.get_page(page_id)
        if page is None:
            raise LookupError("Page not found")
        if self.cleanup_repo is None:
            raise DatabaseError("Cleanup job repository is not available")
        await self.cleanup_repo.enqueue(page_id)
        return {"page_id": page_id, "url": page.url, "status": "deleting"}
