"""Test pages router."""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from grimoire_api.dependencies import get_file_repository, get_page_repository
from grimoire_api.main import app

client = TestClient(app)


class TestPagesRouter:
    """Test pages router endpoints."""

    def test_get_page_success(self) -> None:
        """Test successful page retrieval."""
        mock_page_repo = AsyncMock()
        mock_page_repo.get_by_id.return_value = {
            "id": 123,
            "url": "https://example.com",
            "title": "Test Article",
            "memo": "Test memo",
            "summary": "Test summary",
            "keywords": ["test", "article"],
            "created_at": "2025-01-01T12:00:00Z",
            "updated_at": "2025-01-01T12:05:00Z",
            "weaviate_id": "test-uuid",
            "error_message": None,
        }
        mock_file_repo = AsyncMock()
        mock_file_repo.file_exists.return_value = False

        app.dependency_overrides[get_page_repository] = lambda: mock_page_repo
        app.dependency_overrides[get_file_repository] = lambda: mock_file_repo

        response = client.get("/api/v1/pages/123")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 123
        assert data["url"] == "https://example.com"
        assert data["title"] == "Test Article"

    def test_get_page_not_found(self) -> None:
        """Test page not found."""
        mock_page_repo = AsyncMock()
        mock_page_repo.get_by_id.return_value = None
        mock_file_repo = AsyncMock()

        app.dependency_overrides[get_page_repository] = lambda: mock_page_repo
        app.dependency_overrides[get_file_repository] = lambda: mock_file_repo

        response = client.get("/api/v1/pages/999")

        assert response.status_code == 404
        assert response.json()["detail"] == "Page not found"

    def test_list_pages_success(self) -> None:
        """Test successful pages listing."""
        mock_page_repo = AsyncMock()
        mock_page_repo.list_pages.return_value = (
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

        app.dependency_overrides[get_page_repository] = lambda: mock_page_repo

        response = client.get("/api/v1/pages")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["pages"]) == 1
        assert data["pages"][0]["id"] == 123

    def test_list_pages_with_params(self) -> None:
        """Test pages listing with parameters."""
        mock_page_repo = AsyncMock()
        mock_page_repo.list_pages.return_value = ([], 0)

        app.dependency_overrides[get_page_repository] = lambda: mock_page_repo

        response = client.get("/api/v1/pages?limit=10&offset=5&sort=title&order=asc")

        assert response.status_code == 200
        mock_page_repo.list_pages.assert_called_once_with(
            limit=10, offset=5, sort="title", order="asc", status_filter=None
        )

    def test_list_pages_status_filter_all(self) -> None:
        """Test that status=all passes status_filter=None to repository."""
        mock_page_repo = AsyncMock()
        mock_page_repo.list_pages.return_value = ([], 0)

        app.dependency_overrides[get_page_repository] = lambda: mock_page_repo

        response = client.get("/api/v1/pages?status=all")

        assert response.status_code == 200
        mock_page_repo.list_pages.assert_called_once_with(
            limit=20, offset=0, sort="created_at", order="desc", status_filter=None
        )

    def test_list_pages_status_filter_completed(self) -> None:
        """Test that status=completed is passed to repository."""
        mock_page_repo = AsyncMock()
        mock_page_repo.list_pages.return_value = ([], 0)

        app.dependency_overrides[get_page_repository] = lambda: mock_page_repo

        response = client.get("/api/v1/pages?status=completed")

        assert response.status_code == 200
        mock_page_repo.list_pages.assert_called_once_with(
            limit=20,
            offset=0,
            sort="created_at",
            order="desc",
            status_filter="completed",
        )

    def test_list_pages_status_filter_processing(self) -> None:
        """Test that status=processing is passed to repository."""
        mock_page_repo = AsyncMock()
        mock_page_repo.list_pages.return_value = ([], 0)

        app.dependency_overrides[get_page_repository] = lambda: mock_page_repo

        response = client.get("/api/v1/pages?status=processing")

        assert response.status_code == 200
        mock_page_repo.list_pages.assert_called_once_with(
            limit=20,
            offset=0,
            sort="created_at",
            order="desc",
            status_filter="processing",
        )

    def test_list_pages_status_filter_failed(self) -> None:
        """Test that status=failed is passed to repository."""
        mock_page_repo = AsyncMock()
        mock_page_repo.list_pages.return_value = ([], 0)

        app.dependency_overrides[get_page_repository] = lambda: mock_page_repo

        response = client.get("/api/v1/pages?status=failed")

        assert response.status_code == 200
        mock_page_repo.list_pages.assert_called_once_with(
            limit=20, offset=0, sort="created_at", order="desc", status_filter="failed"
        )
