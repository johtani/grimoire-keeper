"""Test LLM service."""

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from grimoire_api.services.llm_service import LLMService
from grimoire_api.utils.exceptions import LLMServiceError


class TestLLMService:
    """LLMServiceのテストクラス."""

    @pytest.fixture(autouse=True)
    def mock_token_counter(self):
        """テストでは外部トークナイザー解決を避けて決定的に計測する."""
        with patch(
            "grimoire_api.services.llm_service.token_counter",
            side_effect=lambda **kwargs: len(kwargs["text"].encode("utf-8")),
        ):
            yield

    @pytest.fixture
    def mock_file_repo(self: Any) -> Any:
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
    def llm_service(self, mock_file_repo: Any) -> Any:
        """LLMサービスフィクスチャ."""
        return LLMService(file_repo=mock_file_repo, api_key="test_api_key")

    def test_init_with_api_key(self: Any, mock_file_repo: Any) -> None:
        """APIキー指定での初期化テスト."""
        api_key = "test_api_key"
        service = LLMService(file_repo=mock_file_repo, api_key=api_key)
        assert service.api_key == api_key

    def test_init_without_api_key(self: Any, mock_file_repo: Any) -> None:
        """APIキー未指定での初期化テスト."""
        with patch("grimoire_api.services.llm_service.settings") as mock_settings:
            mock_settings.LLM_API_KEY = "settings_api_key"
            mock_settings.LLM_CONTEXT_WINDOW = 32768
            mock_settings.LLM_MAX_OUTPUT_TOKENS = 1024
            mock_settings.LLM_SUMMARY_CONCURRENCY = 3
            service = LLMService(file_repo=mock_file_repo)
            assert service.api_key == "settings_api_key"

    @pytest.mark.asyncio
    async def test_generate_summary_keywords_success(
        self, llm_service: Any, mock_file_repo: Any
    ) -> None:
        """正常な要約・キーワード生成テスト."""
        page_id = 1
        expected_result = {
            "summary": "This is a test summary.",
            "keywords": ["test", "keyword", "example"],
        }

        with patch("grimoire_api.services.llm_service.acompletion") as mock_completion:
            mock_response = MagicMock()
            mock_response.model_dump.return_value = {
                "choices": [{"message": {"content": json.dumps(expected_result)}}]
            }
            mock_completion.return_value = mock_response

            result = await llm_service.generate_summary_keywords(page_id)
            assert result == expected_result

            # ファイル読み込みが呼ばれたことを確認
            mock_file_repo.load_json_file.assert_called_once_with(page_id)

    @pytest.mark.asyncio
    async def test_generate_summary_keywords_no_api_key(
        self: Any, mock_file_repo: Any
    ) -> None:
        """APIキー未設定でのテスト."""
        with patch("grimoire_api.services.llm_service.settings") as mock_settings:
            mock_settings.LLM_API_KEY = None
            mock_settings.LLM_CONTEXT_WINDOW = 32768
            mock_settings.LLM_MAX_OUTPUT_TOKENS = 1024
            mock_settings.LLM_SUMMARY_CONCURRENCY = 3
            service = LLMService(file_repo=mock_file_repo, api_key=None)

            with pytest.raises(LLMServiceError, match="LLM API key is not configured"):
                await service.generate_summary_keywords(1)

    @pytest.mark.asyncio
    async def test_generate_summary_keywords_invalid_api_key(
        self: Any, mock_file_repo: Any
    ) -> None:
        """無効なAPIキーでのテスト."""
        service = LLMService(file_repo=mock_file_repo, api_key="invalid_key")

        with patch(
            "grimoire_api.services.llm_service.acompletion",
            side_effect=Exception("authentication failed"),
        ):
            with pytest.raises(LLMServiceError, match="LLM processing error"):
                await service.generate_summary_keywords(1)

    @pytest.mark.asyncio
    async def test_generate_summary_keywords_invalid_json(
        self: Any, llm_service: Any
    ) -> None:
        """不正なJSON応答のテスト."""
        page_id = 1

        with patch("grimoire_api.services.llm_service.acompletion") as mock_completion:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "invalid json"
            mock_completion.return_value = mock_response

            with pytest.raises(
                LLMServiceError, match="Failed to parse LLM response as JSON"
            ):
                await llm_service.generate_summary_keywords(page_id)

    @pytest.mark.asyncio
    async def test_generate_summary_keywords_invalid_format(
        self: Any, llm_service: Any
    ) -> None:
        """不正なフォーマットの応答テスト."""
        page_id = 1
        invalid_result = {"summary": "test"}  # keywordsが不足

        with patch("grimoire_api.services.llm_service.acompletion") as mock_completion:
            mock_response = MagicMock()
            mock_response.model_dump.return_value = {
                "choices": [{"message": {"content": json.dumps(invalid_result)}}]
            }
            mock_completion.return_value = mock_response

            with pytest.raises(LLMServiceError, match="Invalid LLM response format"):
                await llm_service.generate_summary_keywords(page_id)

    @pytest.mark.asyncio
    async def test_generate_summary_keywords_keywords_not_list(
        self: Any, llm_service: Any
    ) -> None:
        """キーワードがリストでない場合のテスト."""
        page_id = 1
        invalid_result = {"summary": "test summary", "keywords": "not a list"}

        with patch("grimoire_api.services.llm_service.acompletion") as mock_completion:
            mock_response = MagicMock()
            mock_response.model_dump.return_value = {
                "choices": [{"message": {"content": json.dumps(invalid_result)}}]
            }
            mock_completion.return_value = mock_response

            with pytest.raises(LLMServiceError, match="Keywords must be a list"):
                await llm_service.generate_summary_keywords(page_id)

    @pytest.mark.asyncio
    async def test_generate_summary_keywords_completion_error(
        self: Any, llm_service: Any
    ) -> None:
        """LiteLLM呼び出しエラーのテスト."""
        page_id = 1

        with patch("grimoire_api.services.llm_service.acompletion") as mock_completion:
            mock_completion.side_effect = Exception("API error")

            with pytest.raises(LLMServiceError, match="LLM processing error"):
                await llm_service.generate_summary_keywords(page_id)

    def test_build_prompt(self: Any, llm_service: Any) -> None:
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
    async def test_completion_parameters(self: Any, llm_service: Any) -> None:
        """LiteLLM呼び出しパラメータのテスト."""
        page_id = 1
        expected_result = {"summary": "test", "keywords": ["test"]}

        with patch("grimoire_api.services.llm_service.acompletion") as mock_completion:
            mock_response = MagicMock()
            mock_response.model_dump.return_value = {
                "choices": [{"message": {"content": json.dumps(expected_result)}}]
            }
            mock_completion.return_value = mock_response

            await llm_service.generate_summary_keywords(page_id)

            # 呼び出しパラメータを確認
            call_args = mock_completion.call_args
            assert call_args[1]["api_key"] == "test_api_key"
            assert call_args[1]["temperature"] == 0.3
            assert call_args[1]["max_tokens"] == 1024
            assert len(call_args[1]["messages"]) == 1
            assert call_args[1]["messages"][0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_empty_content_raises_clear_error(
        self, llm_service: LLMService, mock_file_repo: Any
    ) -> None:
        """空本文はページID付きのエラーになる."""
        mock_file_repo.load_json_file.return_value["data"]["content"] = "  "

        with pytest.raises(LLMServiceError, match="Empty page content: page_id=7"):
            await llm_service.generate_summary_keywords(7)

    @pytest.mark.asyncio
    async def test_boundary_uses_single_summary(self, llm_service: LLMService) -> None:
        """入力上限ちょうどなら従来の単発要約を使う."""
        llm_service.input_token_limit = 100
        llm_service._count_tokens = MagicMock(return_value=100)
        expected = {"summary": "single", "keywords": ["keyword"]}

        with patch("grimoire_api.services.llm_service.acompletion") as completion:
            completion.return_value = self._response(expected)
            result = await llm_service.generate_summary_keywords(1)

        assert result == expected
        completion.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_long_content_preserves_chunk_order(
        self, mock_file_repo: Any
    ) -> None:
        """分割要約は完了順にかかわらず元のチャンク順で統合する."""
        chunker = MagicMock()
        chunker.chunk_text_with_jina_data.return_value = ["first", "second"]
        service = LLMService(mock_file_repo, api_key="key", chunking_service=chunker)
        service.input_token_limit = 100
        full_prompt = service._build_prompt(
            "Test Title", "This is test content for LLM processing."
        )
        service._count_tokens = MagicMock(
            side_effect=lambda prompt: 101 if prompt == full_prompt else 10
        )

        async def complete(**kwargs: Any) -> MagicMock:
            prompt = kwargs["messages"][0]["content"]
            if "first" in prompt and "second" not in prompt:
                await asyncio.sleep(0.02)
                return self._response({"summary": "summary-first"})
            if "second" in prompt and "first" not in prompt:
                return self._response({"summary": "summary-second"})
            assert prompt.index("summary-first") < prompt.index("summary-second")
            return self._response({"summary": "final", "keywords": ["keyword"]})

        with patch(
            "grimoire_api.services.llm_service.acompletion", side_effect=complete
        ) as completion:
            result = await service.generate_summary_keywords(1)

        assert result == {"summary": "final", "keywords": ["keyword"]}
        assert completion.await_count == 3

    @pytest.mark.asyncio
    async def test_partial_failure_identifies_chunk(self, mock_file_repo: Any) -> None:
        """部分要約失敗は対象チャンクを特定できる."""
        chunker = MagicMock()
        chunker.chunk_text_with_jina_data.return_value = ["first", "second"]
        service = LLMService(mock_file_repo, api_key="key", chunking_service=chunker)
        service.input_token_limit = 100
        full_prompt = service._build_prompt(
            "Test Title", "This is test content for LLM processing."
        )
        service._count_tokens = MagicMock(
            side_effect=lambda prompt: 101 if prompt == full_prompt else 10
        )

        with patch(
            "grimoire_api.services.llm_service.acompletion",
            side_effect=[self._response({"summary": "ok"}), Exception("timeout")],
        ):
            with pytest.raises(LLMServiceError, match=r"chunk=2/2.*timeout"):
                await service.generate_summary_keywords(9)

    @pytest.mark.asyncio
    async def test_chunk_requests_respect_concurrency_limit(
        self, mock_file_repo: Any
    ) -> None:
        """部分要約の同時LLMリクエスト数は設定上限を超えない."""
        chunker = MagicMock()
        chunker.chunk_text_with_jina_data.return_value = ["one", "two", "three"]
        service = LLMService(mock_file_repo, api_key="key", chunking_service=chunker)
        service.semaphore = asyncio.Semaphore(2)
        service.input_token_limit = 100
        full_prompt = service._build_prompt(
            "Test Title", "This is test content for LLM processing."
        )
        service._count_tokens = MagicMock(
            side_effect=lambda prompt: 101 if prompt == full_prompt else 10
        )
        active = 0
        maximum_active = 0

        async def complete(**kwargs: Any) -> MagicMock:
            nonlocal active, maximum_active
            prompt = kwargs["messages"][0]["content"]
            if "最終要約" in prompt:
                return self._response({"summary": "final", "keywords": []})
            active += 1
            maximum_active = max(maximum_active, active)
            await asyncio.sleep(0.01)
            active -= 1
            return self._response({"summary": "partial"})

        with patch(
            "grimoire_api.services.llm_service.acompletion", side_effect=complete
        ):
            await service.generate_summary_keywords(1)

        assert maximum_active == 2

    @pytest.mark.asyncio
    async def test_request_over_input_limit_is_not_sent(
        self, llm_service: LLMService
    ) -> None:
        """上限超過プロンプトはLLMへ送信しない."""
        llm_service.input_token_limit = 10
        llm_service._count_tokens = MagicMock(return_value=11)

        with patch("grimoire_api.services.llm_service.acompletion") as completion:
            with pytest.raises(LLMServiceError, match="input token limit exceeded"):
                await llm_service._complete_json("too long", require_keywords=True)
        completion.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_oversized_integration_is_reduced_hierarchically(
        self, mock_file_repo: Any
    ) -> None:
        """部分要約の統合入力が大きい場合は縮約してから最終要約する."""
        chunker = MagicMock()
        chunker.chunk_text_with_jina_data.return_value = ["first", "second"]
        service = LLMService(mock_file_repo, api_key="key", chunking_service=chunker)
        service.input_token_limit = 100
        full_prompt = service._build_prompt(
            "Test Title", "This is test content for LLM processing."
        )

        def count(prompt: str) -> int:
            if prompt == full_prompt:
                return 101
            if "summary-first" in prompt and "summary-second" in prompt:
                return 101 if "最終要約" in prompt else 10
            return 10

        service._count_tokens = MagicMock(side_effect=count)
        responses = [
            self._response({"summary": "summary-first"}),
            self._response({"summary": "summary-second"}),
            self._response({"summary": "reduced"}),
            self._response({"summary": "final", "keywords": ["keyword"]}),
        ]
        with patch(
            "grimoire_api.services.llm_service.acompletion", side_effect=responses
        ) as completion:
            result = await service.generate_summary_keywords(1)

        assert result["summary"] == "final"
        assert completion.await_count == 4

    @staticmethod
    def _response(result: dict[str, Any]) -> MagicMock:
        response = MagicMock()
        response.model_dump.return_value = {
            "choices": [{"message": {"content": json.dumps(result)}}]
        }
        return response
