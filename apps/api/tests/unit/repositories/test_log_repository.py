"""Test log repository."""

from typing import Any

import pytest
from tests.helpers import get_process_logs


class TestLogRepository:
    """LogRepositoryのテストクラス."""

    @pytest.mark.asyncio
    async def test_create_log(self, log_repo: Any) -> None:
        """ログ作成テスト."""
        url = "https://example.com"
        status = "started"

        log_id = await log_repo.create_log(url, status)
        assert log_id is not None
        assert isinstance(log_id, int)

    @pytest.mark.asyncio
    async def test_create_log_with_page_id(self, log_repo: Any, page_repo: Any) -> None:
        """ページID付きログ作成テスト."""
        url = "https://example.com"
        status = "started"
        page_id = await page_repo.create_page(url, "example")

        log_id = await log_repo.create_log(url, status, page_id)
        assert log_id is not None

    @pytest.mark.asyncio
    async def test_events_are_appended_instead_of_updated(self, log_repo: Any) -> None:
        """進捗イベントは既存行を上書きせず追記する."""
        url = "https://example.com"
        first_id = await log_repo.create_log(url, "job_claimed")
        second_id = await log_repo.create_log(url, "completed")

        logs = await get_process_logs(log_repo)
        assert second_id != first_id
        assert {log["status"] for log in logs} >= {"job_claimed", "completed"}

    @pytest.mark.asyncio
    async def test_has_failed_log_returns_true_when_failed(
        self, log_repo: Any, page_repo: Any
    ) -> None:
        """失敗ログが存在する場合 True を返すテスト."""
        page_id = await page_repo.create_page("https://example.com", "example")
        await log_repo.create_log(
            "https://example.com",
            "failed",
            page_id,
            error_message="some error",
        )

        result = await log_repo.has_failed_log(page_id)
        assert result is True

    @pytest.mark.asyncio
    async def test_has_failed_log_returns_false_when_no_failed(
        self, log_repo: Any
    ) -> None:
        """失敗ログが存在しない場合 False を返すテスト."""
        page_id = 99
        result = await log_repo.has_failed_log(page_id)
        assert result is False

    @pytest.mark.asyncio
    async def test_has_failed_log_returns_false_when_only_succeeded(
        self, log_repo: Any, page_repo: Any
    ) -> None:
        """成功ログのみの場合 False を返すテスト."""
        page_id = await page_repo.create_page("https://example.com", "example")
        await log_repo.create_log("https://example.com", "completed", page_id)

        result = await log_repo.has_failed_log(page_id)
        assert result is False
