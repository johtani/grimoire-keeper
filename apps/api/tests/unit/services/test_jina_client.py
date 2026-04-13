"""Test Jina AI Reader client."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from grimoire_api.services.jina_client import JinaClient
from grimoire_api.utils.exceptions import JinaClientError


class TestJinaClient:
    """JinaClientのテストクラス."""

    def test_init_with_api_key(self: Any) -> None:
        """APIキー指定での初期化テスト."""
        api_key = "test_api_key"
        client = JinaClient(api_key=api_key)
        assert client.api_key == api_key
        assert client.base_url == "https://r.jina.ai"
        assert client._client is None

    def test_init_without_api_key(self: Any) -> None:
        """APIキー未指定での初期化テスト."""
        with patch("grimoire_api.services.jina_client.settings") as mock_settings:
            mock_settings.JINA_API_KEY = "settings_api_key"
            client = JinaClient()
            assert client.api_key == "settings_api_key"
            assert client._client is None

    @pytest.mark.asyncio
    async def test_get_client_creates_client_on_first_call(self: Any) -> None:
        """初回呼び出しで AsyncClient が生成されるテスト."""
        client = JinaClient(api_key="test_key")
        assert client._client is None

        http_client = await client._get_client()

        assert http_client is not None
        assert isinstance(http_client, httpx.AsyncClient)
        assert client._client is http_client
        await client.close()

    @pytest.mark.asyncio
    async def test_get_client_returns_same_instance(self: Any) -> None:
        """2回目の呼び出しで同一インスタンスが返されるテスト."""
        client = JinaClient(api_key="test_key")

        http_client_1 = await client._get_client()
        http_client_2 = await client._get_client()

        assert http_client_1 is http_client_2
        await client.close()

    @pytest.mark.asyncio
    async def test_close_calls_aclose(self: Any) -> None:
        """close() が aclose() を呼び出すテスト."""
        client = JinaClient(api_key="test_key")
        mock_http_client = AsyncMock()
        client._client = mock_http_client

        await client.close()

        mock_http_client.aclose.assert_called_once()
        assert client._client is None

    @pytest.mark.asyncio
    async def test_close_when_client_is_none(self: Any) -> None:
        """_client が None のとき close() は何もしないテスト."""
        client = JinaClient(api_key="test_key")
        assert client._client is None

        # 例外が発生しないことを確認
        await client.close()

    @pytest.mark.asyncio
    async def test_fetch_content_success(self: Any) -> None:
        """正常なコンテンツ取得テスト."""
        client = JinaClient(api_key="test_key")
        test_url = "https://example.com"
        expected_response = {
            "code": 200,
            "data": {"title": "Test Title", "content": "Test content", "url": test_url},
        }

        mock_response = MagicMock()
        mock_response.json.return_value = expected_response
        mock_response.raise_for_status = MagicMock(return_value=None)

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)
        client._client = mock_http_client

        result = await client.fetch_content(test_url)
        assert result == expected_response

    @pytest.mark.asyncio
    async def test_fetch_content_no_api_key(self: Any) -> None:
        """APIキー未設定でのコンテンツ取得テスト."""
        with patch("grimoire_api.services.jina_client.settings") as mock_settings:
            mock_settings.JINA_API_KEY = None
            client = JinaClient(api_key=None)
            test_url = "https://example.com"

            with pytest.raises(JinaClientError, match="Jina API key is not configured"):
                await client.fetch_content(test_url)

    @pytest.mark.asyncio
    async def test_fetch_content_http_error(self: Any) -> None:
        """HTTP エラーのテスト."""
        client = JinaClient(api_key="test_key")
        test_url = "https://example.com"

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        http_error = httpx.HTTPStatusError(
            "401 Unauthorized", request=MagicMock(), response=mock_response
        )
        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(side_effect=http_error)
        client._client = mock_http_client

        with pytest.raises(JinaClientError, match="Jina API HTTP error 401"):
            await client.fetch_content(test_url)

    @pytest.mark.asyncio
    async def test_fetch_content_request_error(self: Any) -> None:
        """リクエストエラーのテスト."""
        client = JinaClient(api_key="test_key")
        test_url = "https://example.com"

        request_error = httpx.RequestError("Connection failed")
        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(side_effect=request_error)
        client._client = mock_http_client

        with pytest.raises(JinaClientError, match="Jina API request error"):
            await client.fetch_content(test_url)

    @pytest.mark.asyncio
    async def test_health_check_success(self: Any) -> None:
        """ヘルスチェック成功テスト."""
        client = JinaClient(api_key="test_key")

        with patch.object(client, "fetch_content", return_value={"status": "ok"}):
            result = await client.health_check()
            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self: Any) -> None:
        """ヘルスチェック失敗テスト."""
        client = JinaClient(api_key="test_key")

        with patch.object(
            client, "fetch_content", side_effect=JinaClientError("API error")
        ):
            result = await client.health_check()
            assert result is False

    @pytest.mark.asyncio
    async def test_fetch_content_timeout(self: Any) -> None:
        """タイムアウト時のテスト."""
        client = JinaClient(api_key="test_key")
        test_url = "https://example.com"

        timeout_error = httpx.TimeoutException("Request timeout")
        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(side_effect=timeout_error)
        client._client = mock_http_client

        with pytest.raises(JinaClientError, match="Jina API request error"):
            await client.fetch_content(test_url)

    @pytest.mark.asyncio
    async def test_fetch_content_rate_limit(self: Any) -> None:
        """429 レートリミット応答のテスト."""
        client = JinaClient(api_key="test_key")
        test_url = "https://example.com"

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Too Many Requests"

        http_error = httpx.HTTPStatusError(
            "429 Too Many Requests", request=MagicMock(), response=mock_response
        )
        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(side_effect=http_error)
        client._client = mock_http_client

        with pytest.raises(JinaClientError, match="Jina API HTTP error 429"):
            await client.fetch_content(test_url)

    @pytest.mark.asyncio
    async def test_fetch_content_invalid_api_key(self: Any) -> None:
        """不正な API キー (401) 時のテスト."""
        client = JinaClient(api_key="invalid_key")
        test_url = "https://example.com"

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        http_error = httpx.HTTPStatusError(
            "401 Unauthorized", request=MagicMock(), response=mock_response
        )
        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(side_effect=http_error)
        client._client = mock_http_client

        with pytest.raises(JinaClientError, match="Jina API HTTP error 401"):
            await client.fetch_content(test_url)

    @pytest.mark.asyncio
    async def test_fetch_content_headers(self: Any) -> None:
        """リクエストヘッダーのテスト."""
        client = JinaClient(api_key="test_key")
        test_url = "https://example.com"

        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {}}
        mock_response.raise_for_status = MagicMock(return_value=None)

        mock_get = AsyncMock(return_value=mock_response)
        mock_http_client = AsyncMock()
        mock_http_client.get = mock_get
        client._client = mock_http_client

        await client.fetch_content(test_url)

        # ヘッダーが正しく設定されていることを確認
        call_args = mock_get.call_args
        headers = call_args[1]["headers"]

        assert headers["Accept"] == "application/json"
        assert headers["Authorization"] == "Bearer test_key"
        assert headers["X-Return-Format"] == "markdown"
        assert headers["X-With-Images-Summary"] == "true"
