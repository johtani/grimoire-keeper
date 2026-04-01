"""Test page repository."""

from typing import Any

import pytest


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
