"""API連携クライアントのテスト"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from grimoire_bot.services.api_client import ApiClient


@pytest.fixture
def api_client():
    """APIクライアントのフィクスチャ"""
    return ApiClient()


@pytest.mark.asyncio
async def test_process_url_success(api_client):
    """URL処理成功テスト"""
    mock_response = {"status": "processing", "page_id": 123}

    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_response
    mock_resp.raise_for_status.return_value = None

    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_resp
        mock_client.return_value.__aenter__.return_value = mock_instance

        result = await api_client.process_url("https://example.com", "test memo")

        assert result == mock_response


@pytest.mark.asyncio
async def test_search_content_success(api_client):
    """検索成功テスト"""
    mock_response = {"results": [{"title": "Test", "url": "https://example.com"}]}

    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_response
    mock_resp.raise_for_status.return_value = None

    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.get.return_value = mock_resp
        mock_client.return_value.__aenter__.return_value = mock_instance

        result = await api_client.search_content("test query")

        assert result == mock_response


@pytest.mark.asyncio
async def test_health_check_success(api_client):
    """ヘルスチェック成功テスト"""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value.status_code = 200

        result = await api_client.health_check()

        assert result is True


@pytest.mark.asyncio
async def test_health_check_failure(api_client):
    """ヘルスチェック失敗テスト"""
    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.side_effect = httpx.RequestError(
            "Connection failed"
        )
        result = await api_client.health_check()

        assert result is False
