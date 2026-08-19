"""Tests for search router."""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from grimoire_api.dependencies import get_search_service, get_weaviate_client
from grimoire_api.main import app
from grimoire_api.models.response import SearchResult

client = TestClient(app)


class TestSearchRouter:
    """検索ルーターテストクラス."""

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

    def test_search_weaviate_unavailable(self) -> None:
        """Weaviate未接続時に503が返ることのテスト."""

        def raise_503() -> None:
            raise HTTPException(status_code=503, detail="Weaviate is not available")

        app.dependency_overrides[get_weaviate_client] = raise_503

        response = client.post(
            "/api/v1/search",
            json={"query": "test query"},
        )

        assert response.status_code == 503
        assert response.json()["detail"] == "Weaviate is not available"

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

    @pytest.mark.parametrize(
        "payload",
        [
            {"query": ""},
            {"query": "   "},
            {"query": "q" * 1001},
            {"query": "query", "limit": 0},
            {"query": "query", "limit": 101},
            {"query": "query", "vector_name": "unknown_vector"},
            {"query": "query", "filters": {"unknown": "value"}},
            {"query": "query", "filters": {"keywords": []}},
            {"query": "query", "filters": {"keywords": ["k"] * 21}},
            {"query": "query", "filters": {"keywords": [" "]}},
            {"query": "query", "filters": {"keywords": ["k" * 101]}},
            {"query": "query", "filters": {"date_from": "not-a-date"}},
            {
                "query": "query",
                "filters": {
                    "date_from": "2025-01-02T00:00:00Z",
                    "date_to": "2025-01-01T00:00:00Z",
                },
            },
            {"query": "query", "exclude_keywords": []},
            {"query": "query", "exclude_keywords": ["k"] * 21},
            {"query": "query", "extra": True},
        ],
    )
    def test_search_rejects_invalid_request(self, payload: dict[str, object]) -> None:
        """制約に違反する検索入力は 422 になる."""
        app.dependency_overrides[get_search_service] = lambda: AsyncMock()

        response = client.post("/api/v1/search", json=payload)

        assert response.status_code == 422

    @pytest.mark.parametrize("limit", [1, 100])
    def test_search_accepts_limit_boundaries(self, limit: int) -> None:
        """検索件数の境界値を受理する."""
        mock_service = AsyncMock()
        mock_service.vector_search.return_value = []
        app.dependency_overrides[get_search_service] = lambda: mock_service

        response = client.post(
            "/api/v1/search", json={"query": "query", "limit": limit}
        )

        assert response.status_code == 200

    def test_search_accepts_mixed_timezone_date_filters(self) -> None:
        """タイムゾーン有無が混在する日時を UTC として検証する."""
        mock_service = AsyncMock()
        mock_service.vector_search.return_value = []
        app.dependency_overrides[get_search_service] = lambda: mock_service

        response = client.post(
            "/api/v1/search",
            json={
                "query": "query",
                "filters": {
                    "date_from": "2025-01-01T00:00:00",
                    "date_to": "2025-01-02T00:00:00Z",
                },
            },
        )

        assert response.status_code == 200
