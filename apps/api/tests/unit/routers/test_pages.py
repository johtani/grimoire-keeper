"""Test pages router."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from grimoire_api.main import app

client = TestClient(app)


class TestPagesRouter:
    """Test pages router endpoints."""

    @patch("grimoire_api.routers.pages.PageRepository")
    def test_get_page_success(self, mock_repo_class):
        """Test successful page retrieval."""
        # Mock repository
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_by_id.return_value = {
            "id": 123,
            "url": "https://example.com",
            "title": "Test Article",
            "memo": "Test memo",
            "summary": "Test summary",
            "keywords": ["test", "article"],
            "created_at": "2025-01-01T12:00:00Z",
            "updated_at": "2025-01-01T12:05:00Z",
            "weaviate_id": "test-uuid",
        }

        response = client.get("/api/v1/pages/123")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 123
        assert data["url"] == "https://example.com"
        assert data["title"] == "Test Article"

    @patch("grimoire_api.routers.pages.PageRepository")
    def test_get_page_not_found(self, mock_repo_class):
        """Test page not found."""
        # Mock repository
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_by_id.return_value = None

        response = client.get("/api/v1/pages/999")

        assert response.status_code == 404
        assert response.json()["detail"] == "Page not found"

    @patch("grimoire_api.routers.pages.PageRepository")
    def test_list_pages_success(self, mock_repo_class):
        """Test successful pages listing."""
        # Mock repository
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.list_pages.return_value = (
            [
                {
                    "id": 123,
                    "url": "https://example.com",
                    "title": "Test Article",
                    "memo": "Test memo",
                    "summary": "Test summary",
                    "keywords": ["test", "article"],
                    "created_at": "2025-01-01T12:00:00Z",
                }
            ],
            1,
        )

        response = client.get("/api/v1/pages")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["pages"]) == 1
        assert data["pages"][0]["id"] == 123

    @patch("grimoire_api.routers.pages.PageRepository")
    def test_list_pages_with_params(self, mock_repo_class):
        """Test pages listing with parameters."""
        # Mock repository
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.list_pages.return_value = ([], 0)

        response = client.get("/api/v1/pages?limit=10&offset=5&sort=title&order=asc")

        assert response.status_code == 200
        # Verify repository was called with correct parameters
        mock_repo.list_pages.assert_called_once_with(
            limit=10, offset=5, sort="title", order="asc"
        )
