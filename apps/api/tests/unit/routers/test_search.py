"""Tests for search router."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from grimoire_api.main import app
from grimoire_api.models.response import SearchResult
from grimoire_api.services.search_service import SearchService

client = TestClient(app)


class TestSearchRouter:
    """検索ルーターテストクラス."""

    @patch("grimoire_api.routers.search.SearchService")
    def test_search_with_default_vector(self, mock_search_service: MagicMock) -> None:
        """デフォルトベクトルでの検索テスト."""
        # モックサービス設定
        mock_instance = AsyncMock()
        mock_instance.vector_search.return_value = [
            SearchResult(
                page_id=1,
                chunk_id=0,
                url="https://example.com",
                title="Test Title",
                memo=None,
                content="Test content",
                summary="Test summary",
                keywords=["test"],
                created_at="2023-01-01T00:00:00Z",
                score=0.85,
            )
        ]
        mock_search_service.return_value = mock_instance

        # リクエスト実行
        response = client.post(
            "/api/v1/search",
            json={"query": "test query", "limit": 5},
        )

        # レスポンス検証
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["query"] == "test query"
        assert len(data["results"]) == 1

        # サービス呼び出し検証
        mock_instance.vector_search.assert_called_once_with(
            query="test query",
            limit=5,
            filters=None,
            vector_name="content_vector",
        )

    @patch("grimoire_api.routers.search.SearchService")
    def test_search_with_custom_vector(self, mock_search_service: MagicMock) -> None:
        """カスタムベクトルでの検索テスト."""
        # モックサービス設定
        mock_instance = AsyncMock()
        mock_instance.vector_search.return_value = [
            SearchResult(
                page_id=2,
                chunk_id=0,
                url="https://title-search.com",
                title="Title Search",
                memo=None,
                content="Content",
                summary="Summary",
                keywords=["title"],
                created_at="2023-02-01T00:00:00Z",
                score=0.92,
            )
        ]
        mock_search_service.return_value = mock_instance

        # リクエスト実行
        response = client.post(
            "/api/v1/search",
            json={
                "query": "title query",
                "limit": 3,
                "vector_name": "title_vector",
            },
        )

        # レスポンス検証
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["query"] == "title query"

        # サービス呼び出し検証
        mock_instance.vector_search.assert_called_once_with(
            query="title query",
            limit=3,
            filters=None,
            vector_name="title_vector",
        )

    @patch("grimoire_api.routers.search.SearchService")
    def test_search_with_filters_and_vector(self, mock_search_service: MagicMock) -> None:
        """フィルターとベクトル指定での検索テスト."""
        # モックサービス設定
        mock_instance = AsyncMock()
        mock_instance.vector_search.return_value = []
        mock_search_service.return_value = mock_instance

        # リクエスト実行
        response = client.post(
            "/api/v1/search",
            json={
                "query": "filtered query",
                "limit": 10,
                "filters": {"url": "example", "keywords": ["test"]},
                "vector_name": "memo_vector",
            },
        )

        # レスポンス検証
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0

        # サービス呼び出し検証
        mock_instance.vector_search.assert_called_once_with(
            query="filtered query",
            limit=10,
            filters={"url": "example", "keywords": ["test"]},
            vector_name="memo_vector",
        )
