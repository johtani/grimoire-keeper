"""Tests for the batch retry script."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from scripts.batch_retry import batch_retry_from_status


@pytest.mark.asyncio
async def test_dry_run_lists_pages_without_starting_reprocessing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dry run lists matching pages without invoking the retry service."""
    page_repository = AsyncMock()
    page_repository.get_pages_by_status.return_value = [
        SimpleNamespace(id=1, url="https://example.com")
    ]
    retry_service = AsyncMock()

    with (
        patch("scripts.batch_retry.DatabaseConnection"),
        patch("scripts.batch_retry.PageRepository", return_value=page_repository),
        patch("scripts.batch_retry.JobRepository"),
        patch("scripts.batch_retry.RetryService", return_value=retry_service),
    ):
        await batch_retry_from_status("download", dry_run=True)

    output = capsys.readouterr().out
    assert "DRY RUN" in output
    assert "Page 1: https://example.com" in output
    retry_service.reprocess_page.assert_not_awaited()
