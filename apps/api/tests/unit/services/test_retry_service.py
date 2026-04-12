"""Test RetryService."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from grimoire_api.models.database import ProcessingStep
from grimoire_api.services.retry_service import RetryService


@pytest.fixture
def mock_services() -> dict:
    """モックサービス群."""
    return {
        "jina_client": AsyncMock(),
        "llm_service": AsyncMock(),
        "vectorizer": AsyncMock(),
        "page_repo": AsyncMock(),
        "log_repo": AsyncMock(),
        "file_repo": AsyncMock(),
    }


@pytest.fixture
def retry_service(mock_services: Any) -> RetryService:
    """RetryService フィクスチャ."""
    return RetryService(
        jina_client=mock_services["jina_client"],
        llm_service=mock_services["llm_service"],
        vectorizer=mock_services["vectorizer"],
        page_repo=mock_services["page_repo"],
        log_repo=mock_services["log_repo"],
        file_repo=mock_services["file_repo"],
    )


class TestRetryServiceSaveMethods:
    """RetryService の _save_download_result / _save_llm_result テストクラス."""

    @pytest.mark.asyncio
    async def test_save_download_result(
        self, retry_service: RetryService, mock_services: Any
    ) -> None:
        """ダウンロード結果保存テスト."""
        log_id = 1
        page_id = 2
        jina_result = {"data": {"title": "Test Title", "content": "Test content"}}

        await retry_service._save_download_result(log_id, page_id, jina_result)

        mock_services["file_repo"].save_json_file.assert_called_once_with(
            page_id, jina_result
        )
        mock_services["page_repo"].update_title_and_step.assert_called_once_with(
            page_id, "Test Title", ProcessingStep.DOWNLOADED
        )
        mock_services["log_repo"].update_status.assert_called_once_with(
            log_id, "download_complete"
        )

    @pytest.mark.asyncio
    async def test_save_llm_result(
        self, retry_service: RetryService, mock_services: Any
    ) -> None:
        """LLM結果保存テスト."""
        log_id = 1
        page_id = 2
        llm_result = {"summary": "Test summary", "keywords": ["test", "keyword"]}

        await retry_service._save_llm_result(log_id, page_id, llm_result)

        mock_services[
            "page_repo"
        ].update_summary_keywords_and_step.assert_called_once_with(
            page_id=page_id,
            summary="Test summary",
            keywords=["test", "keyword"],
            step=ProcessingStep.LLM_PROCESSED,
        )
        mock_services["log_repo"].update_status.assert_called_once_with(
            log_id, "llm_complete"
        )


class TestRetrySinglePage:
    """retry_single_page メソッドのテストクラス."""

    @pytest.mark.asyncio
    async def test_retry_single_page_not_failed(
        self, retry_service: RetryService, mock_services: Any
    ) -> None:
        """失敗ログが存在しない場合 not_failed を返すテスト."""
        mock_page = AsyncMock()
        mock_page.url = "https://example.com"
        mock_services["page_repo"].get_page = AsyncMock(return_value=mock_page)
        mock_services["log_repo"].has_failed_log = AsyncMock(return_value=False)

        result = await retry_service.retry_single_page(1)

        mock_services["log_repo"].has_failed_log.assert_called_once_with(1)
        assert result["status"] == "not_failed"
        assert result["page_id"] == 1

    @pytest.mark.asyncio
    async def test_retry_single_page_uses_has_failed_log(
        self, retry_service: RetryService, mock_services: Any
    ) -> None:
        """retry_single_page が has_failed_log を使用していることを確認."""
        mock_page = AsyncMock()
        mock_page.url = "https://example.com"
        mock_page.last_success_step = None
        mock_services["page_repo"].get_page = AsyncMock(return_value=mock_page)
        mock_services["log_repo"].has_failed_log = AsyncMock(return_value=True)
        mock_services["log_repo"].create_log = AsyncMock(return_value=1)

        with patch.object(retry_service, "_execute_retry_from_point", new=AsyncMock()):
            await retry_service.retry_single_page(1)

        mock_services["log_repo"].has_failed_log.assert_called_once_with(1)


class TestRetryAllFailed:
    """retry_all_failed メソッドのテストクラス."""

    @pytest.mark.asyncio
    async def test_retry_all_failed_logs_error_on_page_failure(
        self, retry_service: RetryService, mock_services: Any
    ) -> None:
        """個別ページのリトライ失敗時に logger.error が呼ばれることを確認."""
        mock_log = AsyncMock()
        mock_log.page_id = 1
        mock_services["log_repo"].get_logs_by_status = AsyncMock(
            return_value=[mock_log]
        )

        error = Exception("retry error")
        with (
            patch.object(
                retry_service, "retry_single_page", side_effect=error
            ) as mock_retry,
            patch("grimoire_api.services.retry_service.logger") as mock_logger,
        ):
            result = await retry_service.retry_all_failed()

        mock_retry.assert_called_once_with(1)
        mock_logger.error.assert_called_once_with(
            "Failed to retry page_id=1: retry error"
        )
        assert result["status"] == "batch_retry_started"
        assert result["retry_count"] == 0

    @pytest.mark.asyncio
    async def test_retry_all_failed_continues_after_single_failure(
        self, retry_service: RetryService, mock_services: Any
    ) -> None:
        """1ページ失敗しても残りページの処理が継続されることを確認."""
        mock_log1 = AsyncMock()
        mock_log1.page_id = 1
        mock_log2 = AsyncMock()
        mock_log2.page_id = 2
        mock_services["log_repo"].get_logs_by_status = AsyncMock(
            return_value=[mock_log1, mock_log2]
        )

        call_count = 0

        async def side_effect(page_id: int) -> dict:
            nonlocal call_count
            call_count += 1
            if page_id == 1:
                raise Exception("page 1 failed")
            return {"status": "retry_started", "page_id": page_id}

        with (
            patch.object(retry_service, "retry_single_page", side_effect=side_effect),
            patch("grimoire_api.services.retry_service.logger") as mock_logger,
        ):
            result = await retry_service.retry_all_failed(delay_seconds=0)

        assert call_count == 2
        mock_logger.error.assert_called_once_with(
            "Failed to retry page_id=1: page 1 failed"
        )
        assert result["retry_count"] == 1
        assert result["total_failed_pages"] == 2
