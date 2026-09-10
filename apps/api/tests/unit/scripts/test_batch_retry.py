"""Tests for the batch retry script."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from grimoire_api.models.database import ProcessingStep
from grimoire_api.utils.exceptions import ResourceConflictError

from scripts.batch_retry import batch_retry_from_status


@pytest.mark.asyncio
async def test_dry_run_lists_pages_without_starting_reprocessing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dry run lists matching pages without invoking the retry service."""
    page_repository = AsyncMock()
    page_repository.get_reprocess_candidates.return_value = [
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


@pytest.mark.parametrize(
    ("from_step", "previous_step"),
    [
        ("download", None),
        ("llm", ProcessingStep.DOWNLOADED),
        ("vectorize", ProcessingStep.LLM_PROCESSED),
    ],
)
async def test_selects_candidates_by_step_before_restart(
    from_step: str,
    previous_step: ProcessingStep | None,
) -> None:
    page_repository = AsyncMock()
    page_repository.get_reprocess_candidates.return_value = []

    with (
        patch("scripts.batch_retry.DatabaseConnection"),
        patch("scripts.batch_retry.PageRepository", return_value=page_repository),
        patch("scripts.batch_retry.JobRepository"),
        patch("scripts.batch_retry.RetryService"),
    ):
        await batch_retry_from_status(from_step, dry_run=True)

    page_repository.get_reprocess_candidates.assert_awaited_once_with(previous_step)


async def test_max_pages_is_applied_to_dry_run_candidates(
    capsys: pytest.CaptureFixture[str],
) -> None:
    page_repository = AsyncMock()
    page_repository.get_reprocess_candidates.return_value = [
        SimpleNamespace(id=1, url="https://one.example.com"),
        SimpleNamespace(id=2, url="https://two.example.com"),
    ]

    with (
        patch("scripts.batch_retry.DatabaseConnection"),
        patch("scripts.batch_retry.PageRepository", return_value=page_repository),
        patch("scripts.batch_retry.JobRepository"),
        patch("scripts.batch_retry.RetryService"),
    ):
        await batch_retry_from_status("llm", max_pages=1, dry_run=True)

    output = capsys.readouterr().out
    assert "Page 1: https://one.example.com" in output
    assert "two.example.com" not in output


async def test_active_job_race_is_skipped(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    page_repository = AsyncMock()
    page_repository.get_reprocess_candidates.return_value = [
        SimpleNamespace(id=1, url="https://example.com")
    ]
    retry_service = AsyncMock()
    retry_service.reprocess_page.side_effect = ResourceConflictError(
        "An active job already exists"
    )
    monkeypatch.setattr("builtins.input", lambda _: "y")

    with (
        patch("scripts.batch_retry.DatabaseConnection"),
        patch("scripts.batch_retry.PageRepository", return_value=page_repository),
        patch("scripts.batch_retry.JobRepository"),
        patch("scripts.batch_retry.RetryService", return_value=retry_service),
    ):
        await batch_retry_from_status("vectorize", interval_seconds=0)

    output = capsys.readouterr().out
    assert "Skipped: An active job already exists" in output
    assert "Skipped: 1" in output
    assert "Errors: 0" in output
