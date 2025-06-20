"""Test LLM service."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from grimoire_api.services.llm_service import LLMService
from grimoire_api.utils.exceptions import LLMServiceError


class TestLLMService:
    """LLMServiceのテストクラス."""

    @pytest.fixture
    def mock_file_repo(self):
        """ファイルリポジトリモック."""
        mock_repo = AsyncMock()
        mock_repo.load_json_file.return_value = {
            "data": {
                "title": "Test Title",
                "content": "This is test content for LLM processing.",
            }
        }
        return mock_repo

    @pytest.fixture
    def llm_service(self, mock_file_repo):
        """LLMサービスフィクスチャ."""
        return LLMService(file_repo=mock_file_repo, api_key="test_api_key")

    def test_init_with_api_key(self, mock_file_repo):
        """APIキー指定での初期化テスト."""
        api_key = "test_api_key"
        service = LLMService(file_repo=mock_file_repo, api_key=api_key)
        assert service.api_key == api_key

    def test_init_without_api_key(self, mock_file_repo):
        """APIキー未指定での初期化テスト."""
        with patch("grimoire_api.services.llm_service.settings") as mock_settings:
            mock_settings.GOOGLE_API_KEY = "settings_api_key"
            service = LLMService(file_repo=mock_file_repo)
            assert service.api_key == "settings_api_key"

    @pytest.mark.asyncio
    async def test_generate_summary_keywords_success(self, llm_service, mock_file_repo):
        """正常な要約・キーワード生成テスト."""
        page_id = 1
        expected_result = {
            "summary": "This is a test summary.",
            "keywords": ["test", "keyword", "example"],
        }

        with patch("grimoire_api.services.llm_service.completion") as mock_completion:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = json.dumps(expected_result)
            mock_completion.return_value = mock_response

            result = await llm_service.generate_summary_keywords(page_id)
            assert result == expected_result

            # ファイル読み込みが呼ばれたことを確認
            mock_file_repo.load_json_file.assert_called_once_with(page_id)

    @pytest.mark.asyncio
    async def test_generate_summary_keywords_no_api_key(self, mock_file_repo):
        """APIキー未設定でのテスト."""
        service = LLMService(file_repo=mock_file_repo, api_key="")

        with pytest.raises(LLMServiceError, match="Google API key is not configured"):
            await service.generate_summary_keywords(1)

    @pytest.mark.asyncio
    async def test_generate_summary_keywords_invalid_json(self, llm_service):
        """不正なJSON応答のテスト."""
        page_id = 1

        with patch("grimoire_api.services.llm_service.completion") as mock_completion:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "invalid json"
            mock_completion.return_value = mock_response

            with pytest.raises(
                LLMServiceError, match="Failed to parse LLM response as JSON"
            ):
                await llm_service.generate_summary_keywords(page_id)

    @pytest.mark.asyncio
    async def test_generate_summary_keywords_invalid_format(self, llm_service):
        """不正なフォーマットの応答テスト."""
        page_id = 1
        invalid_result = {"summary": "test"}  # keywordsが不足

        with patch("grimoire_api.services.llm_service.completion") as mock_completion:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = json.dumps(invalid_result)
            mock_completion.return_value = mock_response

            with pytest.raises(LLMServiceError, match="Invalid LLM response format"):
                await llm_service.generate_summary_keywords(page_id)

    @pytest.mark.asyncio
    async def test_generate_summary_keywords_keywords_not_list(self, llm_service):
        """キーワードがリストでない場合のテスト."""
        page_id = 1
        invalid_result = {"summary": "test summary", "keywords": "not a list"}

        with patch("grimoire_api.services.llm_service.completion") as mock_completion:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = json.dumps(invalid_result)
            mock_completion.return_value = mock_response

            with pytest.raises(LLMServiceError, match="Keywords must be a list"):
                await llm_service.generate_summary_keywords(page_id)

    @pytest.mark.asyncio
    async def test_generate_summary_keywords_completion_error(self, llm_service):
        """LiteLLM呼び出しエラーのテスト."""
        page_id = 1

        with patch("grimoire_api.services.llm_service.completion") as mock_completion:
            mock_completion.side_effect = Exception("API error")

            with pytest.raises(LLMServiceError, match="LLM processing error"):
                await llm_service.generate_summary_keywords(page_id)

    def test_build_prompt(self, llm_service):
        """プロンプト構築テスト."""
        title = "Test Title"
        content = "Test content"

        prompt = llm_service._build_prompt(title, content)

        assert title in prompt
        assert content in prompt
        assert "JSON" in prompt
        assert "summary" in prompt
        assert "keywords" in prompt

    @pytest.mark.asyncio
    async def test_completion_parameters(self, llm_service):
        """LiteLLM呼び出しパラメータのテスト."""
        page_id = 1
        expected_result = {"summary": "test", "keywords": ["test"]}

        with patch("grimoire_api.services.llm_service.completion") as mock_completion:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = json.dumps(expected_result)
            mock_completion.return_value = mock_response

            await llm_service.generate_summary_keywords(page_id)

            # 呼び出しパラメータを確認
            call_args = mock_completion.call_args
            assert call_args[1]["model"] == "gemini/gemini-1.5-flash"
            assert call_args[1]["api_key"] == "test_api_key"
            assert call_args[1]["temperature"] == 0.3
            assert len(call_args[1]["messages"]) == 1
            assert call_args[1]["messages"][0]["role"] == "user"
