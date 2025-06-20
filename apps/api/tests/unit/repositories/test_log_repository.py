"""Test log repository."""

import pytest


class TestLogRepository:
    """LogRepositoryのテストクラス."""

    @pytest.mark.asyncio
    async def test_create_log(self, log_repo):
        """ログ作成テスト."""
        url = "https://example.com"
        status = "started"

        log_id = await log_repo.create_log(url, status)
        assert log_id is not None
        assert isinstance(log_id, int)

    @pytest.mark.asyncio
    async def test_create_log_with_page_id(self, log_repo):
        """ページID付きログ作成テスト."""
        url = "https://example.com"
        status = "started"
        page_id = 1

        log_id = await log_repo.create_log(url, status, page_id)
        assert log_id is not None

        # ログ取得して確認
        log = await log_repo.get_log(log_id)
        assert log.page_id == page_id

    @pytest.mark.asyncio
    async def test_update_status(self, log_repo):
        """ステータス更新テスト."""
        # ログ作成
        url = "https://example.com"
        status = "started"
        log_id = await log_repo.create_log(url, status)

        # ステータス更新
        new_status = "completed"
        await log_repo.update_status(log_id, new_status)

        # 更新確認
        log = await log_repo.get_log(log_id)
        assert log.status == new_status

    @pytest.mark.asyncio
    async def test_update_status_with_error(self, log_repo):
        """エラーメッセージ付きステータス更新テスト."""
        # ログ作成
        url = "https://example.com"
        status = "started"
        log_id = await log_repo.create_log(url, status)

        # エラーステータス更新
        new_status = "failed"
        error_message = "Test error message"
        await log_repo.update_status(log_id, new_status, error_message)

        # 更新確認
        log = await log_repo.get_log(log_id)
        assert log.status == new_status
        assert log.error_message == error_message

    @pytest.mark.asyncio
    async def test_get_log(self, log_repo):
        """ログ取得テスト."""
        url = "https://example.com"
        status = "started"
        page_id = 1

        # ログ作成
        log_id = await log_repo.create_log(url, status, page_id)

        # ログ取得
        log = await log_repo.get_log(log_id)
        assert log is not None
        assert log.id == log_id
        assert log.url == url
        assert log.status == status
        assert log.page_id == page_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_log(self, log_repo):
        """存在しないログの取得テスト."""
        log = await log_repo.get_log(999)
        assert log is None

    @pytest.mark.asyncio
    async def test_get_logs_by_status(self, log_repo):
        """ステータス別ログ取得テスト."""
        # 複数ログ作成
        urls = ["https://example1.com", "https://example2.com", "https://example3.com"]
        statuses = ["started", "completed", "started"]

        log_ids = []
        for url, status in zip(urls, statuses):
            log_id = await log_repo.create_log(url, status)
            log_ids.append(log_id)

        # "started"ステータスのログ取得
        started_logs = await log_repo.get_logs_by_status("started")
        assert len(started_logs) == 2

        # "completed"ステータスのログ取得
        completed_logs = await log_repo.get_logs_by_status("completed")
        assert len(completed_logs) == 1

        # "failed"ステータスのログ取得（存在しない）
        failed_logs = await log_repo.get_logs_by_status("failed")
        assert len(failed_logs) == 0

    @pytest.mark.asyncio
    async def test_logs_ordered_by_created_at(self, log_repo):
        """作成日時順序テスト."""
        # 複数ログ作成
        log_ids = []
        for i in range(3):
            log_id = await log_repo.create_log(f"https://example{i}.com", "started")
            log_ids.append(log_id)

        # ステータス別取得（新しい順）
        logs = await log_repo.get_logs_by_status("started")
        retrieved_ids = [log.id for log in logs]

        # 新しい順（逆順）で取得されることを確認
        assert retrieved_ids == list(reversed(log_ids))
