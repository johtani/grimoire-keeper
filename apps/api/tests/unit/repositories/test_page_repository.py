"""Test page repository."""

from typing import Any

import pytest
from grimoire_api.repositories.log_repository import LogRepository
from grimoire_api.repositories.page_repository import PageRepository


class TestPageStatus:
    """ページステータス判定のテストクラス."""

    @pytest.mark.asyncio
    async def test_get_by_id_status_completed(self, page_repo: Any) -> None:
        """summary と weaviate_id が両方ある場合 completed を返す."""
        page_id = await page_repo.create_page("https://example.com", "Test")
        await page_repo.update_summary_keywords(page_id, "summary text", ["kw"])
        await page_repo.update_weaviate_id(page_id, "weaviate-uuid")

        result = await page_repo.get_by_id(page_id)
        assert result is not None
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_get_by_id_status_processing(self, page_repo: Any) -> None:
        """process_logs に failed がない場合 processing を返す."""
        page_id = await page_repo.create_page("https://example.com", "Test")

        result = await page_repo.get_by_id(page_id)
        assert result is not None
        assert result["status"] == "processing"

    @pytest.mark.asyncio
    async def test_get_by_id_status_failed(self, page_repo: Any, temp_db: Any) -> None:
        """process_logs に failed がある場合 failed を返す."""
        log_repo = LogRepository(db=temp_db)
        page_id = await page_repo.create_page("https://example.com", "Test")
        log_id = await log_repo.create_log("https://example.com", "processing", page_id)
        await log_repo.update_status(log_id, "failed", "error occurred")

        result = await page_repo.get_by_id(page_id)
        assert result is not None
        assert result["status"] == "failed"

    @pytest.mark.asyncio
    async def test_list_pages_status_filter_completed(self, page_repo: Any) -> None:
        """completed フィルターが summary+weaviate_id 両方あるページのみ返す."""
        page_id1 = await page_repo.create_page("https://example1.com", "Title1")
        await page_repo.update_summary_keywords(page_id1, "summary", ["kw"])
        await page_repo.update_weaviate_id(page_id1, "uuid-1")

        await page_repo.create_page("https://example2.com", "Title2")

        pages, total = await page_repo.list_pages(status_filter="completed")
        assert total == 1
        assert pages[0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_list_pages_status_filter_processing(
        self, page_repo: Any, temp_db: Any
    ) -> None:
        """processing フィルターが failed ログのないページのみ返す."""
        log_repo = LogRepository(db=temp_db)

        await page_repo.create_page("https://processing.com", "Processing")

        page_id_failed = await page_repo.create_page("https://failed.com", "Failed")
        log_id = await log_repo.create_log(
            "https://failed.com", "processing", page_id_failed
        )
        await log_repo.update_status(log_id, "failed", "error")

        pages, total = await page_repo.list_pages(status_filter="processing")
        assert total == 1
        assert pages[0]["status"] == "processing"

    @pytest.mark.asyncio
    async def test_list_pages_status_filter_failed(
        self, page_repo: Any, temp_db: Any
    ) -> None:
        """failed フィルターが failed ログのあるページのみ返す."""
        log_repo = LogRepository(db=temp_db)

        await page_repo.create_page("https://processing.com", "Processing")

        page_id_failed = await page_repo.create_page("https://failed.com", "Failed")
        log_id = await log_repo.create_log(
            "https://failed.com", "processing", page_id_failed
        )
        await log_repo.update_status(log_id, "failed", "error")

        pages, total = await page_repo.list_pages(status_filter="failed")
        assert total == 1
        assert pages[0]["status"] == "failed"

    def test_compute_page_status_completed(self, page_repo: PageRepository) -> None:
        """_compute_page_status: summary+weaviate_id あれば completed."""
        assert page_repo._compute_page_status("summary", "uuid", False) == "completed"
        assert page_repo._compute_page_status("summary", "uuid", True) == "completed"

    def test_compute_page_status_failed(self, page_repo: PageRepository) -> None:
        """_compute_page_status: failed log があれば failed."""
        assert page_repo._compute_page_status(None, None, True) == "failed"
        assert page_repo._compute_page_status("summary", None, True) == "failed"

    def test_compute_page_status_processing(self, page_repo: PageRepository) -> None:
        """_compute_page_status: failed log がなければ processing."""
        assert page_repo._compute_page_status(None, None, False) == "processing"
        assert page_repo._compute_page_status("summary", None, False) == "processing"


class TestPageRepository:
    """PageRepositoryのテストクラス."""

    @pytest.mark.asyncio
    async def test_create_page(self, page_repo: Any) -> None:
        """ページ作成テスト."""
        url = "https://example.com"
        title = "Test Title"
        memo = "Test memo"

        page_id = await page_repo.create_page(url, title, memo)
        assert page_id is not None
        assert isinstance(page_id, int)

    @pytest.mark.asyncio
    async def test_get_page(self, page_repo: Any) -> None:
        """ページ取得テスト."""
        url = "https://example.com"
        title = "Test Title"
        memo = "Test memo"

        page_id = await page_repo.create_page(url, title, memo)
        page = await page_repo.get_page(page_id)
        assert page is not None
        assert page.id == page_id
        assert page.url == url
        assert page.title == title
        assert page.memo == memo

    @pytest.mark.asyncio
    async def test_get_nonexistent_page(self, page_repo: Any) -> None:
        """存在しないページの取得テスト."""
        page = await page_repo.get_page(999)
        assert page is None

    @pytest.mark.asyncio
    async def test_get_page_by_url(self, page_repo: Any) -> None:
        """URLでページ取得テスト."""
        url = "https://example.com"
        title = "Test Title"
        memo = "Test memo"

        page_id = await page_repo.create_page(url, title, memo)
        page = await page_repo.get_page_by_url(url)
        assert page is not None
        assert page.id == page_id
        assert page.url == url
        assert page.title == title
        assert page.memo == memo

    @pytest.mark.asyncio
    async def test_get_page_by_nonexistent_url(self, page_repo: Any) -> None:
        """存在しないURLでのページ取得テスト."""
        page = await page_repo.get_page_by_url("https://nonexistent.com")
        assert page is None

    @pytest.mark.asyncio
    async def test_update_summary_keywords(self, page_repo: Any) -> None:
        """要約・キーワード更新テスト."""
        page_id = await page_repo.create_page("https://example.com", "Test Title")

        summary = "This is a test summary."
        keywords = ["keyword1", "keyword2", "keyword3"]
        await page_repo.update_summary_keywords(page_id, summary, keywords)

        page = await page_repo.get_page(page_id)
        assert page.summary == summary
        assert page.keywords == '["keyword1", "keyword2", "keyword3"]'

    @pytest.mark.asyncio
    async def test_update_page_title(self, page_repo: Any) -> None:
        """ページタイトル更新テスト."""
        page_id = await page_repo.create_page("https://example.com", "Old Title")

        new_title = "New Title"
        await page_repo.update_page_title(page_id, new_title)

        page = await page_repo.get_page(page_id)
        assert page.title == new_title

    @pytest.mark.asyncio
    async def test_update_weaviate_id(self, page_repo: Any) -> None:
        """Weaviate ID更新テスト."""
        page_id = await page_repo.create_page("https://example.com", "Test Title")

        weaviate_id = "test-weaviate-id"
        await page_repo.update_weaviate_id(page_id, weaviate_id)

        page = await page_repo.get_page(page_id)
        assert page.weaviate_id == weaviate_id

    @pytest.mark.asyncio
    async def test_get_all_pages(self, page_repo: Any) -> None:
        """全ページ取得テスト."""
        page_ids = []
        for i in range(3):
            page_id = await page_repo.create_page(
                f"https://example{i}.com", f"Test Title {i}"
            )
            page_ids.append(page_id)

        pages = await page_repo.get_all_pages()
        assert len(pages) == 3

        retrieved_ids = [page.id for page in pages]
        assert retrieved_ids == list(reversed(page_ids))

    @pytest.mark.asyncio
    async def test_get_all_pages_with_limit(self, page_repo: Any) -> None:
        """制限付き全ページ取得テスト."""
        for i in range(5):
            await page_repo.create_page(f"https://example{i}.com", f"Test Title {i}")

        pages = await page_repo.get_all_pages(limit=3)
        assert len(pages) == 3

    @pytest.mark.asyncio
    async def test_save_json_file(self, page_repo: Any) -> None:
        """JSONファイル保存テスト."""
        page_id = 1
        test_data = {"data": {"title": "Test Title", "content": "Test content"}}

        await page_repo.save_json_file(page_id, test_data)

        assert await page_repo.file_repo.file_exists(page_id)
