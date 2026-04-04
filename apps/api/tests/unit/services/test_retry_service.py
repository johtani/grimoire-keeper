"""Test RetryService."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from grimoire_api.services.retry_service import RetryService


class TestRetryServiceSaveMethods:
    """RetryService の _save_download_result / _save_llm_result テストクラス."""

    @pytest.fixture
    def mock_services(self) -> dict:
        """モックサービス群."""
        return {
            "jina_client": AsyncMock(),
            "llm_service": AsyncMock(),
            "vectorizer": AsyncMock(),
            "page_repo": AsyncMock(),
            "log_repo": AsyncMock(),
        }

    @pytest.fixture
    def retry_service(self, mock_services: Any) -> RetryService:
        """RetryService フィクスチャ."""
        return RetryService(
            jina_client=mock_services["jina_client"],
            llm_service=mock_services["llm_service"],
            vectorizer=mock_services["vectorizer"],
            page_repo=mock_services["page_repo"],
            log_repo=mock_services["log_repo"],
        )

    @pytest.mark.asyncio
    async def test_save_download_result(
        self, retry_service: RetryService, mock_services: Any
    ) -> None:
        """ダウンロード結果保存テスト."""
        log_id = 1
        page_id = 2
        jina_result = {"data": {"title": "Test Title", "content": "Test content"}}

        await retry_service._save_download_result(log_id, page_id, jina_result)

        mock_services["page_repo"].save_json_file.assert_called_once_with(
            page_id, jina_result
        )
        mock_services["page_repo"].update_title_and_step.assert_called_once_with(
            page_id, "Test Title", "downloaded"
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
            step="llm_processed",
        )
        mock_services["log_repo"].update_status.assert_called_once_with(
            log_id, "llm_complete"
        )


class TestRetryAllFailed:
    """retry_all_failed メソッドのテストクラス."""

    @pytest.fixture
    def mock_services(self) -> dict:
        """モックサービス群."""
        log_repo = AsyncMock()
        page_repo = AsyncMock()
        return {
            "jina_client": AsyncMock(),
            "llm_service": AsyncMock(),
            "vectorizer": AsyncMock(),
            "page_repo": page_repo,
            "log_repo": log_repo,
        }

    @pytest.fixture
    def retry_service(self, mock_services: Any) -> RetryService:
        """RetryService フィクスチャ."""
        return RetryService(
            jina_client=mock_services["jina_client"],
            llm_service=mock_services["llm_service"],
            vectorizer=mock_services["vectorizer"],
            page_repo=mock_services["page_repo"],
            log_repo=mock_services["log_repo"],
        )

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
