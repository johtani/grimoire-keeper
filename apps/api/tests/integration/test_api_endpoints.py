"""Integration tests for API endpoints."""

from unittest.mock import patch

import pytest

# 統合テスト用フィクスチャをインポート
pytest_plugins = ["tests.conftest_integration"]


class TestAPIEndpoints:
    """APIエンドポイントの統合テスト."""

    @pytest.fixture
    def client(self, integration_client):
        """テストクライアント."""
        return integration_client

    def test_root_endpoint(self, client):
        """ルートエンドポイントテスト."""
        response = client.get("/")
        assert response.status_code == 200
        assert "Grimoire Keeper API is running" in response.json()["message"]

    def test_health_check(self, client):
        """ヘルスチェックテスト."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "running" in data["message"]

    @patch("grimoire_api.services.jina_client.JinaClient.fetch_content")
    @patch("grimoire_api.services.llm_service.LLMService.generate_summary_keywords")
    @patch("grimoire_api.services.vectorizer.VectorizerService.vectorize_content")
    def test_process_url_endpoint(self, mock_vectorize, mock_llm, mock_jina, client):
        """URL処理エンドポイントテスト."""
        import uuid

        test_url = f"https://test-{uuid.uuid4().hex[:8]}.example.com"

        # モック設定
        mock_jina.return_value = {
            "data": {"title": "Test Title", "content": "Test content", "url": test_url}
        }
        mock_llm.return_value = {
            "summary": "Test summary",
            "keywords": ["test", "keyword"],
        }
        mock_vectorize.return_value = None

        # リクエスト実行
        response = client.post(
            "/api/v1/process-url",
            json={"url": test_url, "memo": "Test memo"},
        )

        # レスポンス確認
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert "background" in data["message"]

    @patch("grimoire_api.services.search_service.SearchService.vector_search")
    def test_search_endpoint(self, mock_vector_search, client):
        """検索エンドポイントテスト."""
        from grimoire_api.models.response import SearchResult

        # モック設定
        mock_vector_search.return_value = [
            SearchResult(
                page_id=1,
                chunk_id=0,
                url="https://example.com",
                title="Test Title",
                memo="Test memo",
                content="Test content",
                summary="Test summary",
                keywords=["test", "keyword"],
                created_at="2024-01-01T00:00:00",
                score=0.9,
            )
        ]

        # リクエスト実行
        response = client.post(
            "/api/v1/search", json={"query": "test query", "limit": 5}
        )

        # レスポンス確認
        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "test query"
        assert data["total"] == 1
        assert len(data["results"]) == 1

    @patch("grimoire_api.services.search_service.SearchService.keyword_search")
    def test_keyword_search_endpoint(self, mock_keyword_search, client):
        """キーワード検索エンドポイントテスト."""
        # モック設定
        mock_keyword_search.return_value = []

        # リクエスト実行
        response = client.post("/api/v1/search/keywords", json=["keyword1", "keyword2"])

        # レスポンス確認
        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "keyword1 keyword2"
        assert data["total"] == 0
        assert data["results"] == []

    def test_invalid_url_format(self, client):
        """不正なURL形式のテスト."""
        response = client.post(
            "/api/v1/process-url", json={"url": "invalid-url", "memo": "Test memo"}
        )

        # バリデーションエラーを確認
        assert response.status_code == 422

    def test_missing_required_fields(self, client):
        """必須フィールド不足のテスト."""
        response = client.post(
            "/api/v1/process-url",
            json={
                "memo": "Test memo"
                # urlフィールドが不足
            },
        )

        # バリデーションエラーを確認
        assert response.status_code == 422

    def test_search_without_query(self, client):
        """クエリなし検索のテスト."""
        response = client.post(
            "/api/v1/search",
            json={
                "limit": 5
                # queryフィールドが不足
            },
        )

        # バリデーションエラーを確認
        assert response.status_code == 422
