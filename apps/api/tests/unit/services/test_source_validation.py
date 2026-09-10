"""Tests for stored source validation and repair-pending reports."""

import json
from datetime import datetime
from pathlib import Path

import pytest
from grimoire_api.models.database import Page
from grimoire_api.services.source_validation import (
    RepairPendingPage,
    RepairReason,
    classify_stored_source,
    load_repair_report,
    write_repair_report,
)


def _page(page_id: int = 1, url: str = "https://example.com/page") -> Page:
    return Page(
        id=page_id,
        url=url,
        title="title",
        memo=None,
        summary="summary",
        keywords=[],
        created_at=datetime.now(),
        updated_at=datetime.now(),
        weaviate_id="old-id",
    )


def test_classify_stored_source_reports_malformed_404(tmp_path: Path) -> None:
    """%3E URLとJina 404を複数理由として保持する."""
    page = _page(56, "https://example.com/page%3E")
    (tmp_path / "56.json").write_text(
        json.dumps(
            {
                "code": 200,
                "data": {
                    "title": "",
                    "content": "404 body",
                    "httpStatus": 404,
                },
            }
        ),
        encoding="utf-8",
    )

    pending = classify_stored_source(page, tmp_path)

    assert pending is not None
    assert {reason.code for reason in pending.reasons} == {
        "malformed_url_suffix",
        "jina_http_error",
        "missing_title",
    }


def test_classify_stored_source_reports_missing_and_invalid_json(
    tmp_path: Path,
) -> None:
    missing = classify_stored_source(_page(), tmp_path)
    assert missing is not None
    assert [reason.code for reason in missing.reasons] == ["missing_json"]

    (tmp_path / "1.json").write_text("not-json", encoding="utf-8")
    invalid = classify_stored_source(_page(), tmp_path)
    assert invalid is not None
    assert [reason.code for reason in invalid.reasons] == ["invalid_json"]


def test_classify_stored_source_accepts_jina_status_20000(tmp_path: Path) -> None:
    """Jina独自の正常status=20000をHTTPエラー扱いしない."""
    page = _page()
    (tmp_path / "1.json").write_text(
        json.dumps(
            {
                "code": 200,
                "status": 20000,
                "data": {
                    "title": "title",
                    "content": "valid content",
                    "httpStatus": 200,
                },
            }
        ),
        encoding="utf-8",
    )

    assert classify_stored_source(page, tmp_path) is None


def test_write_and_load_repair_report(tmp_path: Path) -> None:
    path = tmp_path / "reports" / "repair-pending.json"
    pending = RepairPendingPage(
        page_id=1,
        url="https://example.com/page",
        reasons=(RepairReason("missing_json", "missing 1.json"),),
    )

    write_repair_report(
        path,
        completed_pages=2,
        scanned_pages=2,
        migration_targets=1,
        repair_pending=[pending],
    )

    report = load_repair_report(path)
    assert report["repair_pending_count"] == 1
    assert report["repair_pending"][0]["page_id"] == 1


def test_load_repair_report_rejects_duplicate_page_ids(tmp_path: Path) -> None:
    path = tmp_path / "repair-pending.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "repair_pending_count": 2,
                "repair_pending": [{"page_id": 1}, {"page_id": 1}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unique"):
        load_repair_report(path)
