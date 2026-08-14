"""Classify stored source data that must be repaired after migration."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from grimoire_api.models.database import Page
from grimoire_api.models.external import FetchedDocument
from grimoire_api.services.chunking_service import ChunkingService
from pydantic import ValidationError


@dataclass(frozen=True)
class RepairReason:
    code: str
    detail: str


@dataclass(frozen=True)
class RepairPendingPage:
    page_id: int
    url: str
    reasons: tuple[RepairReason, ...]


def classify_stored_source(
    page: Page, json_root: Path, chunking_service: ChunkingService | None = None
) -> RepairPendingPage | None:
    """Return repair reasons for one completed page without changing its data."""
    if page.id is None:
        return RepairPendingPage(
            0, page.url, (RepairReason("invalid_page_id", "page ID is missing"),)
        )

    reasons: list[RepairReason] = []
    if page.url.rstrip().lower().endswith((">", "%3e")):
        reasons.append(RepairReason("malformed_url_suffix", "URL ends with > or %3E"))

    source_path = json_root / f"{page.id}.json"
    try:
        source = json.loads(source_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        reasons.append(RepairReason("missing_json", f"missing {source_path.name}"))
        return RepairPendingPage(page.id, page.url, tuple(reasons))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        reasons.append(RepairReason("invalid_json", type(exc).__name__))
        return RepairPendingPage(page.id, page.url, tuple(reasons))

    data = source.get("data") if isinstance(source, dict) else None
    if not isinstance(data, dict):
        reasons.append(RepairReason("invalid_jina_data", "data is not an object"))
        return RepairPendingPage(page.id, page.url, tuple(reasons))

    http_errors = [
        (name, value)
        for name, value in (
            ("code", source.get("code")),
            ("data.httpStatus", data.get("httpStatus")),
        )
        if isinstance(value, int) and not isinstance(value, bool) and value >= 400
    ]
    reasons.extend(
        RepairReason("jina_http_error", f"{name}={value}")
        for name, value in http_errors
    )

    title = data.get("title")
    content = data.get("content")
    if not isinstance(title, str) or not title.strip():
        reasons.append(RepairReason("missing_title", "data.title is empty or invalid"))
    if not isinstance(content, str) or not content.strip():
        reasons.append(
            RepairReason("missing_content", "data.content is empty or invalid")
        )

    if not reasons and chunking_service is not None:
        try:
            document = FetchedDocument.from_jina_response(source, source_url=page.url)
            if not chunking_service.chunk_document(document):
                reasons.append(RepairReason("no_chunks", "no chunks were generated"))
        except (ValidationError, ValueError, TypeError):
            reasons.append(
                RepairReason("invalid_jina_data", "stored response validation failed")
            )

    return RepairPendingPage(page.id, page.url, tuple(reasons)) if reasons else None


def write_repair_report(
    path: Path,
    *,
    completed_pages: int,
    scanned_pages: int,
    migration_targets: int,
    repair_pending: list[RepairPendingPage],
) -> None:
    """Write the deterministic repair-pending migration report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    document: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "completed_pages": completed_pages,
        "scanned_pages": scanned_pages,
        "migration_targets": migration_targets,
        "repair_pending_count": len(repair_pending),
        "repair_pending": [asdict(item) for item in repair_pending],
    }
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def load_repair_report(path: Path) -> dict[str, Any]:
    """Load and minimally validate a repair-pending report."""
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ValueError("unsupported repair report")
    pending = document.get("repair_pending")
    if not isinstance(pending, list):
        raise ValueError("repair_pending must be a list")
    if document.get("repair_pending_count") != len(pending):
        raise ValueError("repair_pending_count does not match the report entries")
    page_ids = [item.get("page_id") for item in pending if isinstance(item, dict)]
    if len(page_ids) != len(pending) or any(
        not isinstance(page_id, int) for page_id in page_ids
    ):
        raise ValueError("every repair-pending entry must have an integer page_id")
    if len(set(page_ids)) != len(page_ids):
        raise ValueError("repair-pending page IDs must be unique")
    return document
