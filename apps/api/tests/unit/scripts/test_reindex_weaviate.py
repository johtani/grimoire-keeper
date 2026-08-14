"""Tests for the Weaviate reindex command."""

import argparse
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from grimoire_api.models.database import Page

from scripts.reindex_weaviate import _positive_int, reindex
from tools.weaviate_1_38_migration.source_validation import (
    RepairPendingPage,
    RepairReason,
)


@pytest.mark.asyncio
async def test_dry_run_targets_all_completed_pages() -> None:
    """上限未指定なら1万件を超えても成功済み全ページを対象にする."""
    page_repo = MagicMock()
    page_repo.count_completed_pages = AsyncMock(return_value=10_001)
    page_repo.get_completed_pages = AsyncMock(return_value=[])

    with (
        patch("scripts.reindex_weaviate.DatabaseConnection") as database_connection,
        patch(
            "scripts.reindex_weaviate.MigrationPageRepository",
            return_value=page_repo,
        ),
    ):
        result = await reindex(max_pages=None, dry_run=True)

    assert result == 0
    database_connection.assert_called_once_with(read_only=True)
    page_repo.get_completed_pages.assert_awaited_once_with(limit=10_001)


@pytest.mark.asyncio
async def test_dry_run_respects_max_pages() -> None:
    """--max-pages 指定時だけ対象件数を制限する."""
    page_repo = MagicMock()
    page_repo.count_completed_pages = AsyncMock(return_value=100)
    page_repo.get_completed_pages = AsyncMock(return_value=[])

    with patch(
        "scripts.reindex_weaviate.MigrationPageRepository", return_value=page_repo
    ):
        result = await reindex(max_pages=5, dry_run=True)

    assert result == 0
    assert page_repo.get_completed_pages.await_args.kwargs["limit"] == 5


def test_positive_int_rejects_zero() -> None:
    """--max-pages は1以上に限定する."""
    with pytest.raises(argparse.ArgumentTypeError):
        _positive_int("0")


@pytest.mark.asyncio
async def test_dry_run_reports_and_excludes_repair_pending_page(
    tmp_path: Path,
) -> None:
    """修復待ちをレポートし、移行対象から除外する."""
    page = Page(
        id=56,
        url="https://example.com/broken%3E",
        title="broken",
        memo=None,
        summary="summary",
        keywords=[],
        created_at=datetime.now(),
        updated_at=datetime.now(),
        weaviate_id="old-id",
    )
    page_repo = MagicMock()
    page_repo.count_completed_pages = AsyncMock(return_value=1)
    page_repo.get_completed_pages = AsyncMock(return_value=[page])
    pending = RepairPendingPage(
        page_id=56,
        url=page.url,
        reasons=(RepairReason("malformed_url_suffix", "URL ends with %3E"),),
    )
    output = tmp_path / "repair-pending.json"

    with (
        patch(
            "scripts.reindex_weaviate.MigrationPageRepository",
            return_value=page_repo,
        ),
        patch("scripts.reindex_weaviate.classify_stored_source", return_value=pending),
    ):
        result = await reindex(None, True, output)

    assert result == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["completed_pages"] == 1
    assert report["migration_targets"] == 0
    assert report["repair_pending_count"] == 1
    assert report["repair_pending"][0]["page_id"] == 56
