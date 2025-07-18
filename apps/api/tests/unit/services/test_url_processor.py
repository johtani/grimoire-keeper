"""Test URL processor service."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from grimoire_api.services.url_processor import UrlProcessorService


class TestUrlProcessorService:
    """UrlProcessorServiceのテストクラス."""

    @pytest.fixture
    def mock_services(self: Any) -> Any:
        """モックサービス群."""
        page_repo = AsyncMock()
        page_repo.get_page_by_url = MagicMock()
        page_repo.create_page = MagicMock()

        log_repo = AsyncMock()
        log_repo.create_log = MagicMock()

        return {
            "jina_client": AsyncMock(),
            "llm_service": AsyncMock(),
            "vectorizer": AsyncMock(),
            "page_repo": page_repo,
            "log_repo": log_repo,
        }

    @pytest.fixture
    def url_processor(self, mock_services: Any) -> Any:
        """URL処理サービスフィクスチャ."""
        return UrlProcessorService(
            jina_client=mock_services["jina_client"],
            llm_service=mock_services["llm_service"],
            vectorizer=mock_services["vectorizer"],
            page_repo=mock_services["page_repo"],
            log_repo=mock_services["log_repo"],
        )

    def test_prepare_url_processing_success(
        self, url_processor, mock_services: Any
    ) -> None:
        """正常なURL処理準備テスト."""
        url = "https://example.com"
        memo = "Test memo"
        log_id = 1
        page_id = 2

        # モック設定
        mock_services["page_repo"].get_page_by_url.return_value = None  # URL重複なし
        mock_services["page_repo"].create_page.return_value = page_id
        mock_services["log_repo"].create_log.return_value = log_id

        # 処理実行
        result = url_processor.prepare_url_processing(url, memo)

        # 結果確認
        assert result["status"] == "prepared"
        assert result["page_id"] == page_id
        assert result["log_id"] == log_id
        assert "prepared" in result["message"]

        # 各ステップが呼ばれたことを確認
        mock_services["log_repo"].create_log.assert_called_once_with(
            url, "started", page_id
        )

    @pytest.mark.asyncio
    async def test_process_url_background_success(
        self, url_processor, mock_services: Any
    ) -> None:
        """バックグラウンド処理テスト."""
        url = "https://example.com"
        log_id = 1
        page_id = 2

        # モック設定
        mock_services["jina_client"].fetch_content.return_value = {
            "data": {"title": "Test Title", "content": "Test content"}
        }
        mock_services["llm_service"].generate_summary_keywords.return_value = {
            "summary": "Test summary",
            "keywords": ["test", "keyword"],
        }

        # 処理実行
        await url_processor.process_url_background(page_id, log_id, url)

        # 各ステップが呼ばれたことを確認
        mock_services["jina_client"].fetch_content.assert_called_once_with(url)
        mock_services["llm_service"].generate_summary_keywords.assert_called_once_with(
            page_id
        )
        mock_services["vectorizer"].vectorize_content.assert_called_once_with(page_id)

    @pytest.mark.asyncio
    async def test_process_url_success(self, url_processor, mock_services: Any) -> None:
        """統合URL処理テスト."""
        url = "https://example.com"
        memo = "Test memo"
        log_id = 1
        page_id = 2

        # モック設定
        mock_services["page_repo"].get_page_by_url.return_value = None  # URL重複なし
        mock_services["page_repo"].create_page.return_value = page_id
        mock_services["log_repo"].create_log.return_value = log_id
        mock_services["jina_client"].fetch_content.return_value = {
            "data": {"title": "Test Title", "content": "Test content"}
        }
        mock_services["llm_service"].generate_summary_keywords.return_value = {
            "summary": "Test summary",
            "keywords": ["test", "keyword"],
        }

        # 処理実行
        result = await url_processor.process_url(url, memo)

        # 結果確認
        assert result["status"] == "success"
        assert result["page_id"] == page_id
        assert "completed successfully" in result["message"]

        # 各ステップが呼ばれたことを確認
        mock_services["log_repo"].create_log.assert_called_once_with(
            url, "started", page_id
        )
        mock_services["jina_client"].fetch_content.assert_called_once_with(url)
        mock_services["llm_service"].generate_summary_keywords.assert_called_once_with(
            page_id
        )
        mock_services["vectorizer"].vectorize_content.assert_called_once_with(page_id)

    @pytest.mark.asyncio
    async def test_process_url_background_jina_error(
        self, url_processor, mock_services
    ):
        """Jina AI Readerエラーのテスト."""
        url = "https://example.com"
        log_id = 1
        page_id = 1

        # モック設定
        mock_services["jina_client"].fetch_content.side_effect = Exception("Jina error")

        # バックグラウンド処理実行（エラーはキャッチされる）
        await url_processor.process_url_background(page_id, log_id, url)

        # エラーログが記録されることを確認
        mock_services["log_repo"].update_status.assert_called_with(
            log_id, "failed", "Jina error"
        )

    @pytest.mark.asyncio
    async def test_process_url_background_llm_error(
        self, url_processor, mock_services: Any
    ) -> None:
        """LLMエラーのテスト."""
        url = "https://example.com"
        log_id = 1
        page_id = 2

        # モック設定
        mock_services["jina_client"].fetch_content.return_value = {
            "data": {"title": "Test Title", "content": "Test content"}
        }
        mock_services["llm_service"].generate_summary_keywords.side_effect = Exception(
            "LLM error"
        )

        # バックグラウンド処理実行（エラーはキャッチされる）
        await url_processor.process_url_background(page_id, log_id, url)

        # エラーログが記録されることを確認
        mock_services["log_repo"].update_status.assert_called_with(
            log_id, "failed", "LLM error"
        )

    @pytest.mark.asyncio
    async def test_save_download_result(
        self, url_processor, mock_services: Any
    ) -> None:
        """ダウンロード結果保存テスト."""
        log_id = 1
        page_id = 2
        jina_result = {"data": {"title": "Test Title", "content": "Test content"}}

        # 処理実行
        await url_processor._save_download_result(log_id, page_id, jina_result)

        # 各メソッドが呼ばれたことを確認
        mock_services["page_repo"].update_page_title.assert_called_once_with(
            page_id, "Test Title"
        )
        mock_services["page_repo"].save_json_file.assert_called_once_with(
            page_id, jina_result
        )
        mock_services["log_repo"].update_status.assert_called_once_with(
            log_id, "download_complete"
        )

    @pytest.mark.asyncio
    async def test_save_llm_result(self, url_processor, mock_services: Any) -> None:
        """LLM結果保存テスト."""
        log_id = 1
        page_id = 2
        llm_result = {"summary": "Test summary", "keywords": ["test", "keyword"]}

        # 処理実行
        await url_processor._save_llm_result(log_id, page_id, llm_result)

        # 各メソッドが呼ばれたことを確認
        mock_services["page_repo"].update_summary_keywords.assert_called_once_with(
            page_id=page_id, summary="Test summary", keywords=["test", "keyword"]
        )
        mock_services["log_repo"].update_status.assert_called_once_with(
            log_id, "llm_complete"
        )

    def test_get_processing_status_completed(
        self, url_processor, mock_services: Any
    ) -> None:
        """完了済み処理状況取得テスト."""
        page_id = 1

        # モックページデータ
        mock_page = MagicMock()
        mock_page.id = page_id
        mock_page.url = "https://example.com"
        mock_page.title = "Test Title"
        mock_page.memo = "Test memo"
        mock_page.summary = "Test summary"
        mock_page.keywords = '["test", "keyword"]'
        mock_page.created_at.isoformat.return_value = "2024-01-01T00:00:00"

        # モックログデータ
        mock_log = MagicMock()
        mock_log.page_id = page_id
        mock_log.status = "completed"
        mock_log.error_message = None

        # モック設定
        mock_services["page_repo"].get_page = MagicMock(return_value=mock_page)
        mock_services["log_repo"].get_logs_by_status = MagicMock(
            return_value=[mock_log]
        )

        # 処理実行
        status = url_processor.get_processing_status(page_id)

        # 結果確認
        assert status["status"] == "completed"
        assert status["page"]["id"] == page_id
        assert status["page"]["title"] == "Test Title"

    def test_get_processing_status_not_found(
        self, url_processor, mock_services: Any
    ) -> None:
        """存在しないページの処理状況取得テスト."""
        page_id = 999

        # モック設定
        mock_services["page_repo"].get_page = MagicMock(return_value=None)

        # 処理実行
        status = url_processor.get_processing_status(page_id)

        # 結果確認
        assert status["status"] == "not_found"
        assert "not found" in status["message"]

    def test_process_url_already_exists(
        self, url_processor, mock_services: Any
    ) -> None:
        """URL重複チェックテスト."""
        url = "https://example.com"
        memo = "Test memo"
        existing_page_id = 123

        # 既存ページのモック
        existing_page = MagicMock()
        existing_page.id = existing_page_id
        mock_services["page_repo"].get_page_by_url.return_value = existing_page

        # 処理実行
        result = url_processor.prepare_url_processing(url, memo)

        # 結果確認
        assert result["status"] == "already_exists"
        assert result["page_id"] == existing_page_id
        assert "already exists" in result["message"]

        # 重複チェックが呼ばれたことを確認
        mock_services["page_repo"].get_page_by_url.assert_called_once_with(url)

        # 新規作成が呼ばれないことを確認
        mock_services["page_repo"].create_page.assert_not_called()
