"""Test page repository."""

import pytest


class TestPageRepository:
    """PageRepositoryのテストクラス."""

    @pytest.mark.asyncio
    async def test_create_page(self, page_repo):
        """ページ作成テスト."""
        url = "https://example.com"
        title = "Test Title"
        memo = "Test memo"

        page_id = await page_repo.create_page(url, title, memo)
        assert page_id is not None
        assert isinstance(page_id, int)

    @pytest.mark.asyncio
    async def test_get_page(self, page_repo):
        """ページ取得テスト."""
        url = "https://example.com"
        title = "Test Title"
        memo = "Test memo"

        # ページ作成
        page_id = await page_repo.create_page(url, title, memo)

        # ページ取得
        page = await page_repo.get_page(page_id)
        assert page is not None
        assert page.id == page_id
        assert page.url == url
        assert page.title == title
        assert page.memo == memo

    @pytest.mark.asyncio
    async def test_get_nonexistent_page(self, page_repo):
        """存在しないページの取得テスト."""
        page = await page_repo.get_page(999)
        assert page is None

    @pytest.mark.asyncio
    async def test_update_summary_keywords(self, page_repo):
        """要約・キーワード更新テスト."""
        # ページ作成
        page_id = await page_repo.create_page("https://example.com", "Test Title")

        # 要約・キーワード更新
        summary = "This is a test summary."
        keywords = ["keyword1", "keyword2", "keyword3"]
        await page_repo.update_summary_keywords(page_id, summary, keywords)

        # 更新確認
        page = await page_repo.get_page(page_id)
        assert page.summary == summary
        assert page.keywords == '["keyword1", "keyword2", "keyword3"]'

    @pytest.mark.asyncio
    async def test_update_weaviate_id(self, page_repo):
        """Weaviate ID更新テスト."""
        # ページ作成
        page_id = await page_repo.create_page("https://example.com", "Test Title")

        # Weaviate ID更新
        weaviate_id = "test-weaviate-id"
        await page_repo.update_weaviate_id(page_id, weaviate_id)

        # 更新確認
        page = await page_repo.get_page(page_id)
        assert page.weaviate_id == weaviate_id

    @pytest.mark.asyncio
    async def test_get_all_pages(self, page_repo):
        """全ページ取得テスト."""
        # 複数ページ作成
        page_ids = []
        for i in range(3):
            page_id = await page_repo.create_page(
                f"https://example{i}.com", f"Test Title {i}"
            )
            page_ids.append(page_id)

        # 全ページ取得
        pages = await page_repo.get_all_pages()
        assert len(pages) == 3

        # 作成順序の確認（新しい順）
        retrieved_ids = [page.id for page in pages]
        assert retrieved_ids == list(reversed(page_ids))

    @pytest.mark.asyncio
    async def test_get_all_pages_with_limit(self, page_repo):
        """制限付き全ページ取得テスト."""
        # 5ページ作成
        for i in range(5):
            await page_repo.create_page(f"https://example{i}.com", f"Test Title {i}")

        # 制限付き取得
        pages = await page_repo.get_all_pages(limit=3)
        assert len(pages) == 3

    @pytest.mark.asyncio
    async def test_save_json_file(self, page_repo):
        """JSONファイル保存テスト."""
        page_id = 1
        test_data = {"data": {"title": "Test Title", "content": "Test content"}}

        await page_repo.save_json_file(page_id, test_data)

        # ファイルが保存されたことを確認
        assert await page_repo.file_repo.file_exists(page_id)
