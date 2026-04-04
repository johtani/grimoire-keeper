"""Tests for search router."""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from grimoire_api.dependencies import get_search_service
from grimoire_api.main import app
from grimoire_api.models.response import SearchResult

client = TestClient(app)


class TestSearchRouter:
    """検索ルーターテストクラス."""

    def setup_method(self) -> None:
        """各テスト前に dependency_overrides をクリア."""
        app.dependency_overrides.clear()

    def teardown_method(self) -> None:
        """各テスト後に dependency_overrides をクリア."""
        app.dependency_overrides.clear()

    def test_search_with_default_vector(self) -> None:
        """デフォルトベクトルでの検索テスト."""
        mock_service = AsyncMock()
        mock_service.vector_search.return_value = [
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
        app.dependency_overrides[get_search_service] = lambda: mock_service

        response = client.post(
            "/api/v1/search",
            json={"query": "test query", "limit": 5},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["query"] == "test query"
        assert len(data["results"]) == 1

        mock_service.vector_search.assert_called_once_with(
            query="test query",
            limit=5,
            filters=None,
            vector_name="content_vector",
            exclude_keywords=None,
        )

    def test_search_with_custom_vector(self) -> None:
        """カスタムベクトルでの検索テスト."""
        mock_service = AsyncMock()
        mock_service.vector_search.return_value = [
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
        app.dependency_overrides[get_search_service] = lambda: mock_service

        response = client.post(
            "/api/v1/search",
            json={
                "query": "title query",
                "limit": 3,
                "vector_name": "title_vector",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["query"] == "title query"

        mock_service.vector_search.assert_called_once_with(
            query="title query",
            limit=3,
            filters=None,
            vector_name="title_vector",
            exclude_keywords=None,
        )

    def test_search_with_filters_and_vector(self) -> None:
        """フィルターとベクトル指定での検索テスト."""
        mock_service = AsyncMock()
        mock_service.vector_search.return_value = []
        app.dependency_overrides[get_search_service] = lambda: mock_service

        response = client.post(
            "/api/v1/search",
            json={
                "query": "filtered query",
                "limit": 10,
                "filters": {"url": "example", "keywords": ["test"]},
                "vector_name": "memo_vector",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0

        mock_service.vector_search.assert_called_once_with(
            query="filtered query",
            limit=10,
            filters={"url": "example", "keywords": ["test"]},
            vector_name="memo_vector",
            exclude_keywords=None,
        )
