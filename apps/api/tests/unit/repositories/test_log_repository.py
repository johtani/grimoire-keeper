"""Test log repository."""

from typing import Any

import pytest


class TestLogRepository:
    """LogRepositoryのテストクラス."""

    def test_create_log(self, log_repo: Any) -> None:
        """ログ作成テスト（同期版）."""
        url = "https://example.com"
        status = "started"

        log_id = log_repo.create_log(url, status)
        assert log_id is not None
        assert isinstance(log_id, int)

    def test_create_log_with_page_id(self, log_repo: Any) -> None:
        """ページID付きログ作成テスト（同期版）."""
        url = "https://example.com"
        status = "started"
        page_id = 1

        log_id = log_repo.create_log(url, status, page_id)
        assert log_id is not None

    @pytest.mark.asyncio
    async def test_update_status(self, log_repo: Any) -> None:
        """ステータス更新テスト."""
        # ログ作成
        url = "https://example.com"
        status = "started"
        log_id = log_repo.create_log(url, status)

        # ステータス更新
        new_status = "completed"
        log_repo.update_status(log_id, new_status)

    def test_get_logs_by_status(self, log_repo: Any) -> None:
        """ステータス別ログ取得テスト（同期版）."""
        # 複数ログ作成
        urls = ["https://example1.com", "https://example2.com", "https://example3.com"]
        statuses = ["started", "completed", "started"]

        for url, status in zip(urls, statuses):
            log_repo.create_log(url, status)

        # "started"ステータスのログ取得
        started_logs = log_repo.get_logs_by_status("started")
        assert len(started_logs) == 2

        # "completed"ステータスのログ取得
        completed_logs = log_repo.get_logs_by_status("completed")
        assert len(completed_logs) == 1

        # "failed"ステータスのログ取得（存在しない）
        failed_logs = log_repo.get_logs_by_status("failed")
        assert len(failed_logs) == 0

    @pytest.mark.asyncio
    async def test_get_logs_by_status_async(self, log_repo: Any) -> None:
        """ステータス別ログ取得テスト（非同期版）."""
        # 複数ログ作成
        urls = ["https://example1.com", "https://example2.com"]
        statuses = ["started", "completed"]

        for url, status in zip(urls, statuses):
            log_repo.create_log(url, status)

        # "started"ステータスのログ取得
        started_logs = log_repo.get_logs_by_status("started")
        assert len(started_logs) == 1

    @pytest.mark.asyncio
    async def test_get_all_logs(self, log_repo: Any) -> None:
        """全ログ取得テスト."""
        # 複数ログ作成
        for i in range(3):
            log_repo.create_log(f"https://example{i}.com", "started")

        # 全ログ取得
        logs = log_repo.get_all_logs()
        assert len(logs) >= 3
