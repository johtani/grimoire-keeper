"""Test page repository."""

from typing import Any

import pytest


class TestPageRepository:
    """PageRepositoryのテストクラス."""

    def test_create_page(self, page_repo: Any) -> None:
        """ページ作成テスト（同期版）."""
        url = "https://example.com"
        title = "Test Title"
        memo = "Test memo"

        page_id = page_repo.create_page(url, title, memo)
        assert page_id is not None
        assert isinstance(page_id, int)

    def test_get_page(self, page_repo: Any) -> None:
        """ページ取得テスト（同期版）."""
        url = "https://example.com"
        title = "Test Title"
        memo = "Test memo"

        # ページ作成
        page_id = page_repo.create_page(url, title, memo)

        # ページ取得
        page = page_repo.get_page(page_id)
        assert page is not None
        assert page.id == page_id
        assert page.url == url
        assert page.title == title
        assert page.memo == memo

    def test_get_nonexistent_page_sync(self, page_repo: Any) -> None:
        """存在しないページの取得テスト（同期版）."""
        page = page_repo.get_page(999)
        assert page is None

    def test_get_page_by_url(self, page_repo: Any) -> None:
        """URLでページ取得テスト（同期版）."""
        url = "https://example.com"
        title = "Test Title"
        memo = "Test memo"

        # ページ作成
        page_id = page_repo.create_page(url, title, memo)

        # URLでページ取得
        page = page_repo.get_page_by_url(url)
        assert page is not None
        assert page.id == page_id
        assert page.url == url
        assert page.title == title
        assert page.memo == memo

    def test_get_page_by_nonexistent_url_sync(self, page_repo: Any) -> None:
        """存在しないURLでのページ取得テスト（同期版）."""
        page = page_repo.get_page_by_url("https://nonexistent.com")
        assert page is None

    @pytest.mark.asyncio
    async def test_update_summary_keywords(self, page_repo: Any) -> None:
        """要約・キーワード更新テスト."""
        # ページ作成
        page_id = page_repo.create_page("https://example.com", "Test Title")

        # 要約・キーワード更新
        summary = "This is a test summary."
        keywords = ["keyword1", "keyword2", "keyword3"]
        page_repo.update_summary_keywords(page_id, summary, keywords)

        # 更新確認
        page = page_repo.get_page(page_id)
        assert page.summary == summary
        assert page.keywords == '["keyword1", "keyword2", "keyword3"]'

    @pytest.mark.asyncio
    async def test_update_page_title(self, page_repo: Any) -> None:
        """ページタイトル更新テスト."""
        # ページ作成
        page_id = page_repo.create_page("https://example.com", "Old Title")

        # タイトル更新
        new_title = "New Title"
        page_repo.update_page_title(page_id, new_title)

        # 更新確認
        page = page_repo.get_page(page_id)
        assert page.title == new_title

    @pytest.mark.asyncio
    async def test_update_weaviate_id(self, page_repo: Any) -> None:
        """Weaviate ID更新テスト."""
        # ページ作成
        page_id = page_repo.create_page("https://example.com", "Test Title")

        # Weaviate ID更新
        weaviate_id = "test-weaviate-id"
        page_repo.update_weaviate_id(page_id, weaviate_id)

        # 更新確認
        page = page_repo.get_page(page_id)
        assert page.weaviate_id == weaviate_id

    @pytest.mark.asyncio
    async def test_get_all_pages(self, page_repo: Any) -> None:
        """全ページ取得テスト."""
        # 複数ページ作成
        page_ids = []
        for i in range(3):
            page_id = page_repo.create_page(
                f"https://example{i}.com", f"Test Title {i}"
            )
            page_ids.append(page_id)

        # 全ページ取得
        pages = page_repo.get_all_pages()
        assert len(pages) == 3

        # 作成順序の確認（新しい順）
        retrieved_ids = [page.id for page in pages]
        assert retrieved_ids == list(reversed(page_ids))

    @pytest.mark.asyncio
    async def test_get_all_pages_with_limit(self, page_repo: Any) -> None:
        """制限付き全ページ取得テスト."""
        # 5ページ作成
        for i in range(5):
            page_repo.create_page(f"https://example{i}.com", f"Test Title {i}")

        # 制限付き取得
        pages = page_repo.get_all_pages(limit=3)
        assert len(pages) == 3

    @pytest.mark.asyncio
    async def test_save_json_file(self, page_repo: Any) -> None:
        """JSONファイル保存テスト."""
        page_id = 1
        test_data = {"data": {"title": "Test Title", "content": "Test content"}}

        page_repo.save_json_file(page_id, test_data)

        # ファイルが保存されたことを確認
        assert await page_repo.file_repo.file_exists(page_id)
