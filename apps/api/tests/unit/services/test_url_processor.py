"""Test URL processor service."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from grimoire_api.models.database import PageStatus
from grimoire_api.repositories.page_repository import PageRepository
from grimoire_api.services.url_processor import UrlProcessorService
from grimoire_api.utils.exceptions import (
    DatabaseError,
    DuplicateUrlError,
    GrimoireAPIError,
    ResourceNotFoundError,
)


class TestUrlProcessorService:
    """UrlProcessorServiceのテストクラス."""

    @pytest.fixture
    def mock_services(self: Any) -> Any:
        """モックサービス群."""
        page_repo = AsyncMock()
        page_repo.get_page_by_url = AsyncMock()
        page_repo.create_page = AsyncMock()
        page_repo.create_page_with_initial_job = AsyncMock()

        return {"page_repo": page_repo}

    @pytest.fixture
    def url_processor(self, mock_services: Any) -> Any:
        """URL処理サービスフィクスチャ."""
        return UrlProcessorService(page_repo=mock_services["page_repo"])

    @pytest.mark.asyncio
    async def test_prepare_url_processing_success(
        self, url_processor, mock_services: Any
    ) -> None:
        """正常なURL処理準備テスト."""
        url = "https://example.com"
        memo = "Test memo"
        log_id = 1
        page_id = 2

        # モック設定
        mock_services["page_repo"].get_page_by_url.return_value = None  # URL重複なし
        mock_services["page_repo"].create_page_with_initial_job.return_value = (
            page_id,
            log_id,
            99,
        )

        # 処理実行
        result = await url_processor.prepare_url_processing(url, memo)

        # 結果確認
        assert result["status"] == "prepared"
        assert result["page_id"] == page_id
        assert result["log_id"] == log_id
        assert result["job_id"] == 99
        assert "prepared" in result["message"]

        mock_services["page_repo"].create_page_with_initial_job.assert_called_once_with(
            url=url, title="Processing...", memo=memo
        )

    @pytest.mark.asyncio
    async def test_get_processing_status_completed(
        self, url_processor, mock_services: Any
    ) -> None:
        """完了済み処理状況取得テスト."""
        page_id = 1

        # モックページデータ
        mock_page = MagicMock()
        mock_page.id = page_id
        mock_page.url = "https://example.com"
        mock_page.title = "Test Title"
        mock_page.memo = "Test memo"
        mock_page.summary = "Test summary"
        mock_page.keywords = ["test", "keyword"]
        mock_page.created_at.isoformat.return_value = "2024-01-01T00:00:00"
        mock_page.status = PageStatus.SUCCEEDED

        # モック設定
        mock_services["page_repo"].get_page = AsyncMock(return_value=mock_page)

        # 処理実行
        status = await url_processor.get_processing_status(page_id)

        # 結果確認
        assert status["status"] == "completed"
        assert status["page"]["id"] == page_id
        assert status["page"]["title"] == "Test Title"

    @pytest.mark.asyncio
    async def test_get_processing_status_not_found(
        self, url_processor, mock_services: Any
    ) -> None:
        """存在しないページの処理状況取得テスト."""
        page_id = 999

        # モック設定
        mock_services["page_repo"].get_page = AsyncMock(return_value=None)

        with pytest.raises(ResourceNotFoundError, match="Page 999 not found"):
            await url_processor.get_processing_status(page_id)

    @pytest.mark.asyncio
    async def test_process_url_already_exists(
        self, url_processor, mock_services: Any
    ) -> None:
        """URL重複チェックテスト."""
        url = "https://example.com"
        memo = "Test memo"
        existing_page_id = 123

        # 既存ページIDのモック
        mock_services["page_repo"].get_page_by_url.return_value = existing_page_id

        # 処理実行
        result = await url_processor.prepare_url_processing(url, memo)

        # 結果確認
        assert result["status"] == "already_exists"
        assert result["page_id"] == existing_page_id
        assert "already exists" in result["message"]

        # 重複チェックが呼ばれたことを確認
        mock_services["page_repo"].get_page_by_url.assert_called_once_with(url)

        # 新規作成が呼ばれないことを確認
        mock_services["page_repo"].create_page.assert_not_called()
        mock_services["page_repo"].create_page_with_initial_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_concurrent_duplicate_uses_typed_repository_error(
        self, url_processor, mock_services: Any
    ) -> None:
        """並行作成の重複を例外メッセージに依存せず処理する."""
        url = "https://example.com/concurrent"
        mock_services["page_repo"].get_page_by_url.side_effect = [None, 123]
        mock_services[
            "page_repo"
        ].create_page_with_initial_job.side_effect = DuplicateUrlError(
            "driver-specific text"
        )

        result = await url_processor.prepare_url_processing(url)

        assert result["status"] == "already_exists"
        assert result["page_id"] == 123

    @pytest.mark.asyncio
    async def test_database_error_message_is_not_used_for_duplicate_detection(
        self, url_processor, mock_services: Any
    ) -> None:
        """UNIQUE風の文字列だけでは重複として扱わない."""
        mock_services["page_repo"].get_page_by_url.return_value = None
        mock_services[
            "page_repo"
        ].create_page_with_initial_job.side_effect = DatabaseError(
            "UNIQUE constraint failed: pages.url"
        )

        with pytest.raises(GrimoireAPIError) as exc_info:
            await url_processor.prepare_url_processing("https://example.com")

        assert "preparation failed" in str(exc_info.value)


class TestConcurrentUrlProcessor:
    """UrlProcessorService 並行処理テストクラス."""

    @pytest.fixture
    def make_url_processor(self, temp_db: Any) -> Any:
        """実際の PageRepository を使った UrlProcessorService を生成するファクトリ."""

        def _make() -> UrlProcessorService:
            page_repo = PageRepository(db=temp_db)
            return UrlProcessorService(page_repo=page_repo)

        return _make

    @pytest.mark.asyncio
    async def test_prepare_url_processing_creates_all_records(
        self, make_url_processor: Any, temp_db: Any
    ) -> None:
        """正常系でページ・開始ログ・初期ジョブを作成する."""
        url = "https://atomic.example.com"

        result = await make_url_processor().prepare_url_processing(url, "memo")

        assert result["status"] == "prepared"
        page = await temp_db.fetch_one(
            "SELECT id, url, memo, status FROM pages WHERE id = ?",
            (result["page_id"],),
        )
        log = await temp_db.fetch_one(
            "SELECT id, page_id, job_id, attempt, url, status "
            "FROM process_logs WHERE id = ?",
            (result["log_id"],),
        )
        job = await temp_db.fetch_one(
            "SELECT id, page_id, kind, status, start_step FROM jobs WHERE id = ?",
            (result["job_id"],),
        )
        assert page is not None
        assert dict(page) == {
            "id": result["page_id"],
            "url": url,
            "memo": "memo",
            "status": "queued",
        }
        assert log is not None
        assert dict(log) == {
            "id": result["log_id"],
            "page_id": result["page_id"],
            "job_id": result["job_id"],
            "attempt": 0,
            "url": url,
            "status": "job_queued",
        }
        assert job is not None
        assert dict(job) == {
            "id": result["job_id"],
            "page_id": result["page_id"],
            "kind": "initial",
            "status": "queued",
            "start_step": "download",
        }

    @pytest.mark.asyncio
    async def test_prepare_url_processing_rolls_back_on_job_insert_failure(
        self, make_url_processor: Any, temp_db: Any
    ) -> None:
        """ジョブ作成失敗時にページとログもロールバックする."""
        url = "https://rollback.example.com"
        await temp_db.execute(
            """
            CREATE TRIGGER fail_initial_job
            BEFORE INSERT ON jobs
            WHEN NEW.kind = 'initial'
            BEGIN
                SELECT RAISE(ABORT, 'job insert failed');
            END
            """
        )

        with pytest.raises(DatabaseError, match="job insert failed"):
            await make_url_processor().page_repo.create_page_with_initial_job(
                url, "Processing...", "memo"
            )

        for table in ("pages", "process_logs", "jobs"):
            row = await temp_db.fetch_one(f"SELECT COUNT(*) AS count FROM {table}")
            assert row is not None and row["count"] == 0

    @pytest.mark.asyncio
    async def test_concurrent_prepare_url_processing_same_url(
        self, make_url_processor: Any, temp_db: Any
    ) -> None:
        """同一 URL への並行 prepare_url_processing は重複レコードを作らない.

        2つの並行リクエストのうち一方が prepared、もう一方が already_exists を返し、
        DB には1件のみ登録されることを検証する。
        """
        url = "https://concurrent.example.com"
        processor1 = make_url_processor()
        processor2 = make_url_processor()

        results = await asyncio.gather(
            processor1.prepare_url_processing(url),
            processor2.prepare_url_processing(url),
            return_exceptions=True,
        )

        # 例外が発生していないことを確認
        for r in results:
            assert not isinstance(r, Exception), f"Unexpected exception: {r}"

        statuses = [r["status"] for r in results]
        assert sorted(statuses) == ["already_exists", "prepared"]

        # DB に重複レコードがないことを確認
        from grimoire_api.repositories.page_repository import PageRepository

        page_repo = PageRepository(db=temp_db)
        pages = await page_repo.get_all_pages()
        assert sum(1 for p in pages if p.url == url) == 1
        page_id = next(p.id for p in pages if p.url == url)
        log_count = await temp_db.fetch_one(
            "SELECT COUNT(*) AS count FROM process_logs WHERE page_id = ?",
            (page_id,),
        )
        job_count = await temp_db.fetch_one(
            "SELECT COUNT(*) AS count FROM jobs WHERE page_id = ?", (page_id,)
        )
        assert log_count is not None and log_count["count"] == 1
        assert job_count is not None and job_count["count"] == 1
