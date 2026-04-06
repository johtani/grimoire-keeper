"""Test page service."""

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from grimoire_api.models.database import Page, ProcessingStep
from grimoire_api.services.page_service import PageService


def make_page(**kwargs: Any) -> Page:
    """テスト用 Page モデルを生成するヘルパー."""
    defaults = {
        "id": 1,
        "url": "https://example.com",
        "title": "Test Title",
        "memo": None,
        "summary": None,
        "keywords": [],
        "weaviate_id": None,
        "last_success_step": None,
        "created_at": datetime(2025, 1, 1, 12, 0, 0),
        "updated_at": datetime(2025, 1, 1, 12, 0, 0),
    }
    defaults.update(kwargs)
    return Page(**defaults)


@pytest.fixture
def page_service() -> PageService:
    """PageService フィクスチャ (すべての依存をモック化)."""
    page_repo = AsyncMock()
    log_repo = AsyncMock()
    file_repo = AsyncMock()
    return PageService(page_repo=page_repo, log_repo=log_repo, file_repo=file_repo)


class TestComputePageStatus:
    """compute_page_status の単体テスト."""

    def test_completed_when_summary_and_weaviate_id(self) -> None:
        """summary と weaviate_id が両方ある場合 completed."""
        assert PageService.compute_page_status("summary", "uuid", False) == "completed"
        assert PageService.compute_page_status("summary", "uuid", True) == "completed"

    def test_failed_when_has_failed_log(self) -> None:
        """failed ログがあれば failed."""
        assert PageService.compute_page_status(None, None, True) == "failed"
        assert PageService.compute_page_status("summary", None, True) == "failed"

    def test_processing_when_no_failed_log(self) -> None:
        """failed ログがなければ processing."""
        assert PageService.compute_page_status(None, None, False) == "processing"
        assert PageService.compute_page_status("summary", None, False) == "processing"


class TestListPages:
    """list_pages のテスト."""

    @pytest.mark.asyncio
    async def test_list_pages_returns_dict_list(
        self, page_service: PageService
    ) -> None:
        """list_pages がステータス付きの辞書リストを返す."""
        page = make_page(id=1, summary="s", weaviate_id="uuid")
        page_service.page_repo.list_pages.return_value = ([page], 1)  # type: ignore[attr-defined]
        page_service.log_repo.get_failed_page_ids.return_value = set()  # type: ignore[attr-defined]
        page_service.file_repo.get_existing_page_ids.return_value = {1}  # type: ignore[attr-defined]

        result, total = await page_service.list_pages()

        assert total == 1
        assert len(result) == 1
        assert result[0]["id"] == 1
        assert result[0]["status"] == "completed"
        assert result[0]["has_json_file"] is True

    @pytest.mark.asyncio
    async def test_list_pages_status_processing(
        self, page_service: PageService
    ) -> None:
        """failed ログなし → processing ステータス."""
        page = make_page(id=2, summary=None, weaviate_id=None)
        page_service.page_repo.list_pages.return_value = ([page], 1)  # type: ignore[attr-defined]
        page_service.log_repo.get_failed_page_ids.return_value = set()  # type: ignore[attr-defined]
        page_service.file_repo.get_existing_page_ids.return_value = set()  # type: ignore[attr-defined]

        result, total = await page_service.list_pages()

        assert result[0]["status"] == "processing"
        assert result[0]["has_json_file"] is False

    @pytest.mark.asyncio
    async def test_list_pages_status_failed(self, page_service: PageService) -> None:
        """failed ログあり → failed ステータス."""
        page = make_page(id=3, summary=None, weaviate_id=None)
        page_service.page_repo.list_pages.return_value = ([page], 1)  # type: ignore[attr-defined]
        page_service.log_repo.get_failed_page_ids.return_value = {3}  # type: ignore[attr-defined]
        page_service.file_repo.get_existing_page_ids.return_value = set()  # type: ignore[attr-defined]

        result, _ = await page_service.list_pages()

        assert result[0]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_list_pages_passes_params_to_repo(
        self, page_service: PageService
    ) -> None:
        """list_pages がパラメータをリポジトリに正しく渡す."""
        page_service.page_repo.list_pages.return_value = ([], 0)  # type: ignore[attr-defined]
        page_service.log_repo.get_failed_page_ids.return_value = set()  # type: ignore[attr-defined]
        page_service.file_repo.get_existing_page_ids.return_value = set()  # type: ignore[attr-defined]

        await page_service.list_pages(
            limit=10, offset=5, sort="title", order="asc", status_filter="completed"
        )

        page_service.page_repo.list_pages.assert_called_once_with(  # type: ignore[attr-defined]
            limit=10, offset=5, sort="title", order="asc", status_filter="completed"
        )

    @pytest.mark.asyncio
    async def test_list_pages_empty(self, page_service: PageService) -> None:
        """ページが0件の場合."""
        page_service.page_repo.list_pages.return_value = ([], 0)  # type: ignore[attr-defined]
        page_service.log_repo.get_failed_page_ids.return_value = set()  # type: ignore[attr-defined]
        page_service.file_repo.get_existing_page_ids.return_value = set()  # type: ignore[attr-defined]

        result, total = await page_service.list_pages()

        assert result == []
        assert total == 0


class TestGetPageDetail:
    """get_page_detail のテスト."""

    @pytest.mark.asyncio
    async def test_get_page_detail_not_found(self, page_service: PageService) -> None:
        """存在しないページは None を返す."""
        page_service.page_repo.get_page.return_value = None  # type: ignore[attr-defined]

        result = await page_service.get_page_detail(999)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_page_detail_completed(self, page_service: PageService) -> None:
        """summary + weaviate_id ありなら completed."""
        page = make_page(id=1, summary="summary text", weaviate_id="uuid-1")
        page_service.page_repo.get_page.return_value = page  # type: ignore[attr-defined]
        page_service.log_repo.get_latest_error.return_value = None  # type: ignore[attr-defined]
        page_service.log_repo.get_failed_page_ids.return_value = set()  # type: ignore[attr-defined]

        result = await page_service.get_page_detail(1)

        assert result is not None
        assert result["id"] == 1
        assert result["status"] == "completed"
        assert result["error_message"] is None

    @pytest.mark.asyncio
    async def test_get_page_detail_failed_with_error(
        self, page_service: PageService
    ) -> None:
        """failed ログありなら failed + エラーメッセージ."""
        page = make_page(id=2, summary=None, weaviate_id=None)
        page_service.page_repo.get_page.return_value = page  # type: ignore[attr-defined]
        page_service.log_repo.get_latest_error.return_value = "some error"  # type: ignore[attr-defined]
        page_service.log_repo.get_failed_page_ids.return_value = {2}  # type: ignore[attr-defined]

        result = await page_service.get_page_detail(2)

        assert result is not None
        assert result["status"] == "failed"
        assert result["error_message"] == "some error"

    @pytest.mark.asyncio
    async def test_get_page_detail_processing(self, page_service: PageService) -> None:
        """failed ログなし、未完了なら processing."""
        page = make_page(id=3, summary=None, weaviate_id=None)
        page_service.page_repo.get_page.return_value = page  # type: ignore[attr-defined]
        page_service.log_repo.get_latest_error.return_value = None  # type: ignore[attr-defined]
        page_service.log_repo.get_failed_page_ids.return_value = set()  # type: ignore[attr-defined]

        result = await page_service.get_page_detail(3)

        assert result is not None
        assert result["status"] == "processing"

    @pytest.mark.asyncio
    async def test_get_page_detail_includes_all_fields(
        self, page_service: PageService
    ) -> None:
        """返却辞書に必要なフィールドが全て含まれる."""
        page = make_page(
            id=1,
            summary="s",
            weaviate_id="uuid",
            keywords=["kw1", "kw2"],
            last_success_step=ProcessingStep.VECTORIZED,
        )
        page_service.page_repo.get_page.return_value = page  # type: ignore[attr-defined]
        page_service.log_repo.get_latest_error.return_value = None  # type: ignore[attr-defined]
        page_service.log_repo.get_failed_page_ids.return_value = set()  # type: ignore[attr-defined]

        result = await page_service.get_page_detail(1)

        assert result is not None
        expected_keys = {
            "id",
            "url",
            "title",
            "memo",
            "summary",
            "keywords",
            "created_at",
            "updated_at",
            "weaviate_id",
            "status",
            "error_message",
            "last_success_step",
        }
        assert expected_keys.issubset(result.keys())
        assert result["keywords"] == ["kw1", "kw2"]
        assert result["last_success_step"] == ProcessingStep.VECTORIZED
