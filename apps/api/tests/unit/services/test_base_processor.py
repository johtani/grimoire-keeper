"""Test BaseProcessorService._run_pipeline_from."""

from typing import Any
from unittest.mock import AsyncMock, call

import pytest
from grimoire_api.models.database import ProcessingStep
from grimoire_api.services.base_processor import BaseProcessorService


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
def base_processor(mock_services: Any) -> BaseProcessorService:
    """BaseProcessorService フィクスチャ."""
    return BaseProcessorService(
        jina_client=mock_services["jina_client"],
        llm_service=mock_services["llm_service"],
        vectorizer=mock_services["vectorizer"],
        page_repo=mock_services["page_repo"],
        log_repo=mock_services["log_repo"],
        file_repo=mock_services["file_repo"],
    )


class TestRunPipelineFrom:
    """_run_pipeline_from メソッドのテストクラス."""

    @pytest.mark.asyncio
    async def test_from_download_runs_all_steps(
        self, base_processor: BaseProcessorService, mock_services: Any
    ) -> None:
        """download から開始した場合に全ステップが実行される."""
        page_id = 1
        log_id = 10
        url = "https://example.com"

        mock_services["jina_client"].fetch_content.return_value = {
            "data": {"title": "Test Title", "content": "Test content"}
        }
        mock_services["llm_service"].generate_summary_keywords.return_value = {
            "summary": "Test summary",
            "keywords": ["test"],
        }

        await base_processor._run_pipeline_from(page_id, log_id, url, "download")

        mock_services["jina_client"].fetch_content.assert_called_once_with(url)
        mock_services["llm_service"].generate_summary_keywords.assert_called_once_with(
            page_id
        )
        mock_services["vectorizer"].vectorize_content.assert_called_once_with(page_id)

    @pytest.mark.asyncio
    async def test_from_llm_skips_download(
        self, base_processor: BaseProcessorService, mock_services: Any
    ) -> None:
        """llm から開始した場合は download ステップをスキップする."""
        page_id = 1
        log_id = 10
        url = "https://example.com"

        mock_services["llm_service"].generate_summary_keywords.return_value = {
            "summary": "Test summary",
            "keywords": ["test"],
        }

        await base_processor._run_pipeline_from(page_id, log_id, url, "llm")

        mock_services["jina_client"].fetch_content.assert_not_called()
        mock_services["llm_service"].generate_summary_keywords.assert_called_once_with(
            page_id
        )
        mock_services["vectorizer"].vectorize_content.assert_called_once_with(page_id)

    @pytest.mark.asyncio
    async def test_from_vectorize_skips_download_and_llm(
        self, base_processor: BaseProcessorService, mock_services: Any
    ) -> None:
        """vectorize から開始した場合は download・llm ステップをスキップする."""
        page_id = 1
        log_id = 10
        url = "https://example.com"

        await base_processor._run_pipeline_from(page_id, log_id, url, "vectorize")

        mock_services["jina_client"].fetch_content.assert_not_called()
        mock_services["llm_service"].generate_summary_keywords.assert_not_called()
        mock_services["vectorizer"].vectorize_content.assert_called_once_with(page_id)

    @pytest.mark.asyncio
    async def test_completion_steps_called_after_success(
        self, base_processor: BaseProcessorService, mock_services: Any
    ) -> None:
        """正常完了時に VECTORIZED と COMPLETED の両ステップが更新される."""
        page_id = 1
        log_id = 10
        url = "https://example.com"

        await base_processor._run_pipeline_from(page_id, log_id, url, "vectorize")

        mock_services["page_repo"].update_success_step.assert_any_call(
            page_id, ProcessingStep.VECTORIZED
        )
        mock_services["page_repo"].update_success_step.assert_any_call(
            page_id, ProcessingStep.COMPLETED
        )
        mock_services["log_repo"].update_status.assert_any_call(
            log_id, "vectorize_complete"
        )
        mock_services["log_repo"].update_status.assert_any_call(log_id, "completed")

    @pytest.mark.asyncio
    async def test_vectorize_failure_calls_clear_weaviate_id(
        self, base_processor: BaseProcessorService, mock_services: Any
    ) -> None:
        """vectorize 失敗時に clear_weaviate_id が呼ばれて例外が再発生する."""
        page_id = 1
        log_id = 10
        url = "https://example.com"

        mock_services["vectorizer"].vectorize_content.side_effect = Exception(
            "Weaviate error"
        )

        with pytest.raises(Exception, match="Weaviate error"):
            await base_processor._run_pipeline_from(page_id, log_id, url, "vectorize")

        mock_services["page_repo"].clear_weaviate_id.assert_called_once_with(page_id)

    @pytest.mark.asyncio
    async def test_vectorize_failure_does_not_call_completed(
        self, base_processor: BaseProcessorService, mock_services: Any
    ) -> None:
        """vectorize 失敗時に COMPLETED ステップが更新されない."""
        page_id = 1
        log_id = 10
        url = "https://example.com"

        mock_services["vectorizer"].vectorize_content.side_effect = Exception(
            "Weaviate error"
        )

        with pytest.raises(Exception):
            await base_processor._run_pipeline_from(page_id, log_id, url, "vectorize")

        completed_calls = [
            c
            for c in mock_services["page_repo"].update_success_step.call_args_list
            if c == call(page_id, ProcessingStep.COMPLETED)
        ]
        assert len(completed_calls) == 0

    @pytest.mark.asyncio
    async def test_download_failure_propagates(
        self, base_processor: BaseProcessorService, mock_services: Any
    ) -> None:
        """download 失敗時に例外が伝播する."""
        page_id = 1
        log_id = 10
        url = "https://example.com"

        mock_services["jina_client"].fetch_content.side_effect = Exception("Jina error")

        with pytest.raises(Exception, match="Jina error"):
            await base_processor._run_pipeline_from(page_id, log_id, url, "download")

        mock_services["llm_service"].generate_summary_keywords.assert_not_called()
        mock_services["vectorizer"].vectorize_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_failure_propagates(
        self, base_processor: BaseProcessorService, mock_services: Any
    ) -> None:
        """llm 失敗時に例外が伝播する."""
        page_id = 1
        log_id = 10
        url = "https://example.com"

        mock_services["llm_service"].generate_summary_keywords.side_effect = Exception(
            "LLM error"
        )

        with pytest.raises(Exception, match="LLM error"):
            await base_processor._run_pipeline_from(page_id, log_id, url, "llm")

        mock_services["vectorizer"].vectorize_content.assert_not_called()
