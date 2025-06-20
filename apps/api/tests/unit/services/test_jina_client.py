"""Test Jina AI Reader client."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from grimoire_api.services.jina_client import JinaClient
from grimoire_api.utils.exceptions import JinaClientError


class TestJinaClient:
    """JinaClientのテストクラス."""

    def test_init_with_api_key(self):
        """APIキー指定での初期化テスト."""
        api_key = "test_api_key"
        client = JinaClient(api_key=api_key)
        assert client.api_key == api_key
        assert client.base_url == "https://r.jina.ai"

    def test_init_without_api_key(self):
        """APIキー未指定での初期化テスト."""
        with patch("grimoire_api.services.jina_client.settings") as mock_settings:
            mock_settings.JINA_API_KEY = "settings_api_key"
            client = JinaClient()
            assert client.api_key == "settings_api_key"

    @pytest.mark.asyncio
    async def test_fetch_content_success(self):
        """正常なコンテンツ取得テスト."""
        client = JinaClient(api_key="test_key")
        test_url = "https://example.com"
        expected_response = {
            "code": 200,
            "data": {"title": "Test Title", "content": "Test content", "url": test_url},
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.json.return_value = expected_response
            mock_response.raise_for_status.return_value = None

            mock_client.return_value.__aenter__.return_value.get.return_value = (
                mock_response
            )

            result = await client.fetch_content(test_url)
            assert result == expected_response

    @pytest.mark.asyncio
    async def test_fetch_content_no_api_key(self):
        """APIキー未設定でのコンテンツ取得テスト."""
        client = JinaClient(api_key="")
        test_url = "https://example.com"

        with pytest.raises(JinaClientError, match="Jina API key is not configured"):
            await client.fetch_content(test_url)

    @pytest.mark.asyncio
    async def test_fetch_content_http_error(self):
        """HTTP エラーのテスト."""
        client = JinaClient(api_key="test_key")
        test_url = "https://example.com"

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 401
            mock_response.text = "Unauthorized"

            http_error = httpx.HTTPStatusError(
                "401 Unauthorized", request=AsyncMock(), response=mock_response
            )
            mock_client.return_value.__aenter__.return_value.get.side_effect = (
                http_error
            )

            with pytest.raises(JinaClientError, match="Jina API HTTP error 401"):
                await client.fetch_content(test_url)

    @pytest.mark.asyncio
    async def test_fetch_content_request_error(self):
        """リクエストエラーのテスト."""
        client = JinaClient(api_key="test_key")
        test_url = "https://example.com"

        with patch("httpx.AsyncClient") as mock_client:
            request_error = httpx.RequestError("Connection failed")
            mock_client.return_value.__aenter__.return_value.get.side_effect = (
                request_error
            )

            with pytest.raises(JinaClientError, match="Jina API request error"):
                await client.fetch_content(test_url)

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """ヘルスチェック成功テスト."""
        client = JinaClient(api_key="test_key")

        with patch.object(client, "fetch_content", return_value={"status": "ok"}):
            result = await client.health_check()
            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """ヘルスチェック失敗テスト."""
        client = JinaClient(api_key="test_key")

        with patch.object(
            client, "fetch_content", side_effect=JinaClientError("API error")
        ):
            result = await client.health_check()
            assert result is False

    @pytest.mark.asyncio
    async def test_fetch_content_headers(self):
        """リクエストヘッダーのテスト."""
        client = JinaClient(api_key="test_key")
        test_url = "https://example.com"

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.json.return_value = {"data": {}}
            mock_response.raise_for_status.return_value = None

            mock_get = mock_client.return_value.__aenter__.return_value.get
            mock_get.return_value = mock_response

            await client.fetch_content(test_url)

            # ヘッダーが正しく設定されていることを確認
            call_args = mock_get.call_args
            headers = call_args[1]["headers"]

            assert headers["Accept"] == "application/json"
            assert headers["Authorization"] == "Bearer test_key"
            assert headers["X-Return-Format"] == "markdown"
            assert headers["X-With-Images-Summary"] == "true"
