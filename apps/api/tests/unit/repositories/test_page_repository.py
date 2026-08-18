"""Test page repository."""

import asyncio
from datetime import datetime, timedelta
from typing import Any

import pytest
from grimoire_api.models.database import Page, PageStatus
from grimoire_api.repositories.repair_repository import RepairRepository
from grimoire_api.utils.exceptions import DatabaseError


async def test_delete_pending_repair_page_is_atomic(temp_db, page_repo) -> None:
    page_id = await page_repo.create_page("https://delete.example.com", "title")
    await RepairRepository(temp_db).upsert_pending(
        page_id, "scan", [{"code": "invalid", "detail": "bad"}]
    )
    await temp_db.execute(
        "INSERT INTO process_logs (page_id, url, status) VALUES (?, ?, ?)",
        (page_id, "https://delete.example.com", "failed"),
    )
    await temp_db.execute(
        "INSERT INTO jobs (page_id, kind, status, start_step) VALUES (?, ?, ?, ?)",
        (page_id, "retry", "failed", "download"),
    )

    await temp_db.execute(
        "CREATE TRIGGER reject_test_page_delete BEFORE DELETE ON pages "
        "BEGIN SELECT RAISE(ABORT, 'test rollback'); END"
    )
    with pytest.raises(DatabaseError, match="test rollback"):
        await page_repo.delete_pending_repair_page(page_id)

    for table in ("pages", "process_logs", "jobs", "repair_cases"):
        row = await temp_db.fetch_one(
            f"SELECT COUNT(*) AS count FROM {table} WHERE "
            + ("id=?" if table == "pages" else "page_id=?"),
            (page_id,),
        )
        assert row is not None and row["count"] == 1


class TestListPages:
    """list_pages の純粋SQLテスト."""

    @pytest.mark.asyncio
    async def test_list_pages_returns_page_models(self, page_repo: Any) -> None:
        """list_pages が Page モデルのリストを返す."""
        page_id = await page_repo.create_page("https://example.com", "Title")
        await page_repo.update_summary_keywords(page_id, "summary", ["kw"])
        await page_repo.update_weaviate_id(page_id, "uuid-1")

        pages, total = await page_repo.list_pages()
        assert total == 1
        assert len(pages) == 1
        assert isinstance(pages[0], Page)
        assert pages[0].id == page_id

    @pytest.mark.asyncio
    async def test_list_pages_status_filter_completed(self, page_repo: Any) -> None:
        """completed フィルターが summary+weaviate_id 両方あるページのみ返す."""
        page_id1 = await page_repo.create_page("https://example1.com", "Title1")
        await page_repo.update_summary_keywords(page_id1, "summary", ["kw"])
        await page_repo.update_weaviate_id(page_id1, "uuid-1")
        await page_repo.update_status(page_id1, PageStatus.SUCCEEDED)

        await page_repo.create_page("https://example2.com", "Title2")

        pages, total = await page_repo.list_pages(status_filter="completed")
        assert total == 1
        assert pages[0].weaviate_id == "uuid-1"

    @pytest.mark.asyncio
    async def test_list_pages_status_filter_processing(
        self, page_repo: Any, temp_db: Any
    ) -> None:
        """processing フィルターが failed ログのないページのみ返す."""
        await page_repo.create_page("https://processing.com", "Processing")

        page_id_failed = await page_repo.create_page("https://failed.com", "Failed")
        await page_repo.update_status(page_id_failed, PageStatus.FAILED)

        pages, total = await page_repo.list_pages(status_filter="processing")
        assert total == 1
        assert pages[0].url == "https://processing.com"

    @pytest.mark.asyncio
    async def test_list_pages_status_filter_failed(
        self, page_repo: Any, temp_db: Any
    ) -> None:
        """failed フィルターが failed ログのあるページのみ返す."""
        await page_repo.create_page("https://processing.com", "Processing")

        page_id_failed = await page_repo.create_page("https://failed.com", "Failed")
        await page_repo.update_status(page_id_failed, PageStatus.FAILED)

        pages, total = await page_repo.list_pages(status_filter="failed")
        assert total == 1
        assert pages[0].url == "https://failed.com"

    @pytest.mark.asyncio
    async def test_list_pages_invalid_sort_field(self, page_repo: Any) -> None:
        """無効な sort フィールドで ValueError が送出される."""
        with pytest.raises(ValueError, match="Invalid sort field"):
            await page_repo.list_pages(sort="invalid_field")

    @pytest.mark.asyncio
    async def test_list_pages_invalid_order(self, page_repo: Any) -> None:
        """無効な order で ValueError が送出される."""
        with pytest.raises(ValueError, match="Invalid order"):
            await page_repo.list_pages(order="random")


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
    async def test_get_pages_by_ids(self, page_repo: Any) -> None:
        """複数ページを一括取得し、IDをキーに返す."""
        first_id = await page_repo.create_page("https://one.example", "One")
        second_id = await page_repo.create_page("https://two.example", "Two")

        pages = await page_repo.get_pages_by_ids([second_id, first_id, 999])

        assert set(pages) == {first_id, second_id}
        assert pages[first_id].title == "One"

    @pytest.mark.asyncio
    async def test_get_searchable_page_ids_applies_filters(
        self, page_repo: Any
    ) -> None:
        """本文検索用のページ属性・除外キーワードをSQLiteで絞り込む."""
        target_id = await page_repo.create_page(
            "https://docs.example/python", "Python", "memo"
        )
        await page_repo.update_summary_keywords(
            target_id, "summary", ["python", "asyncio"]
        )
        await page_repo.update_status(target_id, PageStatus.SUCCEEDED)

        excluded_id = await page_repo.create_page(
            "https://docs.example/old-python", "Old Python"
        )
        await page_repo.update_summary_keywords(
            excluded_id, "summary", ["python", "legacy"]
        )
        await page_repo.update_status(excluded_id, PageStatus.SUCCEEDED)

        result = await page_repo.get_searchable_page_ids(
            filters={"url": "docs.example", "keywords": ["python"]},
            exclude_keywords=["legacy"],
        )

        assert result == [target_id]

    @pytest.mark.asyncio
    async def test_get_searchable_page_ids_applies_date_range(
        self, page_repo: Any
    ) -> None:
        """本文検索用の日付範囲で対象ページを絞り込む."""
        page_id = await page_repo.create_page("https://docs.example", "Docs")
        await page_repo.update_status(page_id, PageStatus.SUCCEEDED)

        page = await page_repo.get_page(page_id)
        assert page is not None

        result = await page_repo.get_searchable_page_ids(
            filters={
                "date_from": page.created_at - timedelta(seconds=1),
                "date_to": page.created_at + timedelta(seconds=1),
            }
        )
        outside = await page_repo.get_searchable_page_ids(
            filters={"date_from": datetime.now() + timedelta(days=1)}
        )

        assert result == [page_id]
        assert outside == []

    @pytest.mark.asyncio
    async def test_get_nonexistent_page(self, page_repo: Any) -> None:
        """存在しないページの取得テスト."""
        page = await page_repo.get_page(999)
        assert page is None

    @pytest.mark.asyncio
    async def test_get_page_by_url(self, page_repo: Any) -> None:
        """URLでページIDを取得するテスト."""
        url = "https://example.com"
        title = "Test Title"
        memo = "Test memo"

        page_id = await page_repo.create_page(url, title, memo)
        result = await page_repo.get_page_by_url(url)
        assert result is not None
        assert isinstance(result, int)
        assert result == page_id

    @pytest.mark.asyncio
    async def test_get_page_by_nonexistent_url(self, page_repo: Any) -> None:
        """存在しないURLでのページ取得テスト."""
        result = await page_repo.get_page_by_url("https://nonexistent.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_summary_keywords(self, page_repo: Any) -> None:
        """要約・キーワード更新テスト."""
        page_id = await page_repo.create_page("https://example.com", "Test Title")

        summary = "This is a test summary."
        keywords = ["keyword1", "keyword2", "keyword3"]
        await page_repo.update_summary_keywords(page_id, summary, keywords)

        page = await page_repo.get_page(page_id)
        assert page.summary == summary
        assert page.keywords == ["keyword1", "keyword2", "keyword3"]

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
    async def test_get_pages_invalid_sort_field(self, page_repo: Any) -> None:
        """無効な sort_by フィールドで ValueError が送出される."""
        with pytest.raises(ValueError, match="Invalid sort field"):
            await page_repo.get_pages(sort_by="invalid_field")

    @pytest.mark.asyncio
    async def test_get_pages_invalid_order(self, page_repo: Any) -> None:
        """無効な order で ValueError が送出される."""
        with pytest.raises(ValueError, match="Invalid order"):
            await page_repo.get_pages(order="random")

    @pytest.mark.asyncio
    async def test_save_json_file(self, page_repo: Any, file_repo: Any) -> None:
        """JSONファイル保存テスト."""
        page_id = 1
        test_data = {"data": {"title": "Test Title", "content": "Test content"}}

        await file_repo.save_json_file(page_id, test_data)

        assert await file_repo.file_exists(page_id)


class TestConcurrentPageRepository:
    """PageRepository 並行処理テストクラス."""

    @pytest.mark.asyncio
    async def test_concurrent_create_page_same_url(self, page_repo: Any) -> None:
        """同一 URL への並行 create_page は重複レコードを作らない.

        UNIQUE 制約により一方は成功し、もう一方は DatabaseError になる。
        DB には1件のみ存在することを検証する。
        """
        url = "https://concurrent.example.com"

        results = await asyncio.gather(
            page_repo.create_page(url, "Title A"),
            page_repo.create_page(url, "Title B"),
            return_exceptions=True,
        )

        successes = [r for r in results if isinstance(r, int)]
        errors = [r for r in results if isinstance(r, Exception)]

        # 1件だけ成功し、1件は UNIQUE 制約エラーになる
        assert len(successes) == 1
        assert len(errors) == 1

        # DB には重複レコードが存在しない
        page_id = await page_repo.get_page_by_url(url)
        assert page_id == successes[0]
        pages = await page_repo.get_all_pages()
        assert sum(1 for p in pages if p.url == url) == 1
