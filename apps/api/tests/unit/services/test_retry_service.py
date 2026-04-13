"""Test RetryService."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from grimoire_api.models.database import ProcessingStep
from grimoire_api.services.retry_service import RetryService
from grimoire_api.utils.exceptions import GrimoireAPIError


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


class TestGetRetryStartPoint:
    """get_retry_start_point メソッドのテストクラス."""

    @pytest.mark.asyncio
    async def test_page_not_found_raises_error(
        self, retry_service: RetryService, mock_services: Any
    ) -> None:
        """ページが存在しない場合 GrimoireAPIError を raise するテスト."""
        mock_services["page_repo"].get_page = AsyncMock(return_value=None)

        with pytest.raises(GrimoireAPIError, match="Page 1 not found"):
            await retry_service.get_retry_start_point(1)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "last_success_step, expected",
        [
            (None, "download"),
            (ProcessingStep.DOWNLOADED, "llm"),
            (ProcessingStep.LLM_PROCESSED, "vectorize"),
            (ProcessingStep.VECTORIZED, "complete"),
            (ProcessingStep.COMPLETED, "download"),  # else ブランチ
        ],
    )
    async def test_start_point_by_step(
        self,
        retry_service: RetryService,
        mock_services: Any,
        last_success_step: ProcessingStep | None,
        expected: str,
    ) -> None:
        """last_success_step に応じた開始ポイントを返すテスト."""
        mock_page = MagicMock()
        mock_page.last_success_step = last_success_step
        mock_services["page_repo"].get_page = AsyncMock(return_value=mock_page)

        result = await retry_service.get_retry_start_point(1)

        assert result == expected


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
    async def test_retry_single_page_page_not_found(
        self, retry_service: RetryService, mock_services: Any
    ) -> None:
        """ページが存在しない場合 GrimoireAPIError を raise するテスト."""
        mock_services["page_repo"].get_page = AsyncMock(return_value=None)

        with pytest.raises(GrimoireAPIError, match="Retry failed"):
            await retry_service.retry_single_page(1)

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
    async def test_retry_single_page_already_completed(
        self, retry_service: RetryService, mock_services: Any
    ) -> None:
        """start_point が complete のとき already_completed を返すテスト."""
        mock_page = MagicMock()
        mock_page.url = "https://example.com"
        mock_page.last_success_step = ProcessingStep.VECTORIZED
        mock_services["page_repo"].get_page = AsyncMock(return_value=mock_page)
        mock_services["log_repo"].has_failed_log = AsyncMock(return_value=True)

        result = await retry_service.retry_single_page(1)

        assert result["status"] == "already_completed"
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

    @pytest.mark.asyncio
    async def test_retry_single_page_calls_create_log_and_execute(
        self, retry_service: RetryService, mock_services: Any
    ) -> None:
        """正常リトライ時に create_log と _execute_retry_from_point が呼ばれること."""
        mock_page = MagicMock()
        mock_page.url = "https://example.com"
        mock_page.last_success_step = None
        mock_services["page_repo"].get_page = AsyncMock(return_value=mock_page)
        mock_services["log_repo"].has_failed_log = AsyncMock(return_value=True)
        mock_services["log_repo"].create_log = AsyncMock(return_value=42)

        mock_execute = AsyncMock()
        with patch.object(retry_service, "_execute_retry_from_point", new=mock_execute):
            result = await retry_service.retry_single_page(1)

        mock_services["log_repo"].create_log.assert_called_once_with(
            "https://example.com", "retry_started", 1
        )
        mock_execute.assert_called_once_with(1, 42, "https://example.com", "download")
        assert result["status"] == "retry_started"
        assert result["restart_from"] == "download"


class TestReprocessPage:
    """reprocess_page メソッドのテストクラス."""

    @pytest.mark.asyncio
    async def test_reprocess_page_not_found_raises_error(
        self, retry_service: RetryService, mock_services: Any
    ) -> None:
        """ページが存在しない場合 GrimoireAPIError を raise するテスト."""
        mock_services["page_repo"].get_page = AsyncMock(return_value=None)

        with pytest.raises(GrimoireAPIError, match="Reprocess failed"):
            await retry_service.reprocess_page(1)

    @pytest.mark.asyncio
    async def test_reprocess_page_auto_complete_starts_from_vectorize(
        self, retry_service: RetryService, mock_services: Any
    ) -> None:
        """from_step=auto で complete のとき vectorize から開始するテスト."""
        mock_page = MagicMock()
        mock_page.url = "https://example.com"
        mock_page.last_success_step = ProcessingStep.VECTORIZED
        mock_services["page_repo"].get_page = AsyncMock(return_value=mock_page)
        mock_services["log_repo"].create_log = AsyncMock(return_value=10)

        mock_execute = AsyncMock()
        with patch.object(retry_service, "_execute_retry_from_point", new=mock_execute):
            result = await retry_service.reprocess_page(1, from_step="auto")

        mock_execute.assert_called_once_with(1, 10, "https://example.com", "vectorize")
        assert result["status"] == "reprocess_started"
        assert result["restart_from"] == "vectorize"

    @pytest.mark.asyncio
    async def test_reprocess_page_auto_non_complete_uses_start_point(
        self, retry_service: RetryService, mock_services: Any
    ) -> None:
        """from_step=auto で complete 以外のとき start_point をそのまま使うテスト."""
        mock_page = MagicMock()
        mock_page.url = "https://example.com"
        mock_page.last_success_step = ProcessingStep.DOWNLOADED
        mock_services["page_repo"].get_page = AsyncMock(return_value=mock_page)
        mock_services["log_repo"].create_log = AsyncMock(return_value=11)

        mock_execute = AsyncMock()
        with patch.object(retry_service, "_execute_retry_from_point", new=mock_execute):
            result = await retry_service.reprocess_page(1, from_step="auto")

        mock_execute.assert_called_once_with(1, 11, "https://example.com", "llm")
        assert result["restart_from"] == "llm"

    @pytest.mark.asyncio
    async def test_reprocess_page_explicit_from_step(
        self, retry_service: RetryService, mock_services: Any
    ) -> None:
        """from_step を明示指定したとき指定ステップから開始するテスト."""
        mock_page = MagicMock()
        mock_page.url = "https://example.com"
        mock_services["page_repo"].get_page = AsyncMock(return_value=mock_page)
        mock_services["log_repo"].create_log = AsyncMock(return_value=12)

        mock_execute = AsyncMock()
        with patch.object(retry_service, "_execute_retry_from_point", new=mock_execute):
            result = await retry_service.reprocess_page(1, from_step="download")

        mock_execute.assert_called_once_with(1, 12, "https://example.com", "download")
        assert result["restart_from"] == "download"


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
    async def test_retry_all_failed_no_failed_pages(
        self, retry_service: RetryService, mock_services: Any
    ) -> None:
        """失敗ページが存在しない場合 no_failed_pages を返すテスト."""
        mock_services["log_repo"].get_logs_by_status = AsyncMock(return_value=[])

        result = await retry_service.retry_all_failed()

        assert result["status"] == "no_failed_pages"
        assert result["total_failed_pages"] == 0
        assert result["retry_count"] == 0

    @pytest.mark.asyncio
    async def test_retry_all_failed_max_retries_limits_count(
        self, retry_service: RetryService, mock_services: Any
    ) -> None:
        """max_retries を指定したとき指定件数以内に切り捨てるテスト."""
        mock_logs = [MagicMock(page_id=i) for i in range(1, 6)]
        mock_services["log_repo"].get_logs_by_status = AsyncMock(return_value=mock_logs)

        with patch.object(
            retry_service,
            "retry_single_page",
            new=AsyncMock(return_value={"status": "retry_started"}),
        ):
            result = await retry_service.retry_all_failed(
                max_retries=2, delay_seconds=0
            )

        assert result["total_failed_pages"] == 2
        assert result["retry_count"] == 2

    @pytest.mark.asyncio
    async def test_retry_all_failed_calls_sleep_when_delay_positive(
        self, retry_service: RetryService, mock_services: Any
    ) -> None:
        """delay_seconds > 0 のとき asyncio.sleep が呼ばれることを確認するテスト."""
        mock_log = MagicMock()
        mock_log.page_id = 1
        mock_services["log_repo"].get_logs_by_status = AsyncMock(
            return_value=[mock_log]
        )

        with (
            patch.object(
                retry_service,
                "retry_single_page",
                new=AsyncMock(return_value={"status": "retry_started"}),
            ),
            patch("asyncio.sleep", new=AsyncMock()) as mock_sleep,
        ):
            await retry_service.retry_all_failed(delay_seconds=1)

        mock_sleep.assert_called_once_with(1)

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


class TestExecuteRetryFromPoint:
    """_execute_retry_from_point メソッドのテストクラス."""

    @pytest.mark.asyncio
    async def test_execute_calls_run_pipeline_from(
        self, retry_service: RetryService
    ) -> None:
        """正常実行時に _run_pipeline_from が正しい引数で呼ばれるテスト."""
        mock_pipeline = AsyncMock()
        with patch.object(retry_service, "_run_pipeline_from", new=mock_pipeline):
            await retry_service._execute_retry_from_point(
                page_id=1, log_id=10, url="https://example.com", start_point="download"
            )

        mock_pipeline.assert_called_once_with(
            page_id=1,
            log_id=10,
            url="https://example.com",
            start_point="download",
        )

    @pytest.mark.asyncio
    async def test_execute_updates_log_on_exception(
        self, retry_service: RetryService, mock_services: Any
    ) -> None:
        """例外発生時に update_status が 'failed' で呼ばれ再 raise されるテスト."""
        error = Exception("pipeline error")
        with patch.object(retry_service, "_run_pipeline_from", side_effect=error):
            with pytest.raises(Exception, match="pipeline error"):
                await retry_service._execute_retry_from_point(
                    page_id=1,
                    log_id=10,
                    url="https://example.com",
                    start_point="llm",
                )

        mock_services["log_repo"].update_status.assert_called_once_with(
            10, "failed", "pipeline error"
        )
