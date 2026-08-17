"""Test pages router."""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from grimoire_api.dependencies import (
    get_file_repository,
    get_page_service,
    get_repair_service,
)
from grimoire_api.main import app

client = TestClient(app)


class TestPagesRouter:
    """Test pages router endpoints."""

    def test_get_page_success(self) -> None:
        """Test successful page retrieval."""
        mock_page_service = AsyncMock()
        mock_page_service.get_page_detail.return_value = {
            "id": 123,
            "url": "https://example.com",
            "title": "Test Article",
            "memo": "Test memo",
            "summary": "Test summary",
            "keywords": ["test", "article"],
            "created_at": "2025-01-01T12:00:00Z",
            "updated_at": "2025-01-01T12:05:00Z",
            "weaviate_id": "test-uuid",
            "status": "completed",
            "error_message": None,
            "last_success_step": None,
        }
        mock_file_repo = AsyncMock()
        mock_file_repo.file_exists.return_value = False

        app.dependency_overrides[get_page_service] = lambda: mock_page_service
        app.dependency_overrides[get_file_repository] = lambda: mock_file_repo

        response = client.get("/api/v1/pages/123")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 123
        assert data["url"] == "https://example.com"
        assert data["title"] == "Test Article"
        assert data["created_at"] == "2025-01-01T12:00:00Z"
        assert data["error_message"] is None
        assert data["has_json_file"] is False

    def test_get_page_not_found(self) -> None:
        """Test page not found."""
        mock_page_service = AsyncMock()
        mock_page_service.get_page_detail.return_value = None
        mock_file_repo = AsyncMock()

        app.dependency_overrides[get_page_service] = lambda: mock_page_service
        app.dependency_overrides[get_file_repository] = lambda: mock_file_repo

        response = client.get("/api/v1/pages/999")

        assert response.status_code == 404
        assert response.json()["detail"] == "Page not found"

    def test_list_pages_success(self) -> None:
        """Test successful pages listing."""
        mock_page_service = AsyncMock()
        mock_page_service.list_pages.return_value = (
            [
                {
                    "id": 123,
                    "url": "https://example.com",
                    "title": "Test Article",
                    "memo": "Test memo",
                    "summary": "Test summary",
                    "created_at": "2025-01-01T12:00:00Z",
                    "status": "completed",
                    "has_json_file": False,
                }
            ],
            1,
        )

        app.dependency_overrides[get_page_service] = lambda: mock_page_service

        response = client.get("/api/v1/pages")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["pages"]) == 1
        assert data["pages"][0]["id"] == 123
        assert data["pages"][0]["created_at"] == "2025-01-01T12:00:00Z"
        assert data["status_filter"] == "all"

    def test_list_pages_with_params(self) -> None:
        """Test pages listing with parameters."""
        mock_page_service = AsyncMock()
        mock_page_service.list_pages.return_value = ([], 0)

        app.dependency_overrides[get_page_service] = lambda: mock_page_service

        response = client.get("/api/v1/pages?limit=10&offset=5&sort=title&order=asc")

        assert response.status_code == 200
        mock_page_service.list_pages.assert_called_once_with(
            limit=10, offset=5, sort="title", order="asc", status_filter=None
        )

    def test_list_pages_status_filter_all(self) -> None:
        """Test that status=all passes status_filter=None to service."""
        mock_page_service = AsyncMock()
        mock_page_service.list_pages.return_value = ([], 0)

        app.dependency_overrides[get_page_service] = lambda: mock_page_service

        response = client.get("/api/v1/pages?status=all")

        assert response.status_code == 200
        mock_page_service.list_pages.assert_called_once_with(
            limit=20, offset=0, sort="created_at", order="desc", status_filter=None
        )

    def test_list_pages_status_filter_completed(self) -> None:
        """Test that status=completed is passed to service."""
        mock_page_service = AsyncMock()
        mock_page_service.list_pages.return_value = ([], 0)

        app.dependency_overrides[get_page_service] = lambda: mock_page_service

        response = client.get("/api/v1/pages?status=completed")

        assert response.status_code == 200
        mock_page_service.list_pages.assert_called_once_with(
            limit=20,
            offset=0,
            sort="created_at",
            order="desc",
            status_filter="completed",
        )

    def test_list_pages_status_filter_processing(self) -> None:
        """Test that status=processing is passed to service."""
        mock_page_service = AsyncMock()
        mock_page_service.list_pages.return_value = ([], 0)

        app.dependency_overrides[get_page_service] = lambda: mock_page_service

        response = client.get("/api/v1/pages?status=processing")

        assert response.status_code == 200
        mock_page_service.list_pages.assert_called_once_with(
            limit=20,
            offset=0,
            sort="created_at",
            order="desc",
            status_filter="processing",
        )

    def test_list_pages_status_filter_failed(self) -> None:
        """Test that status=failed is passed to service."""
        mock_page_service = AsyncMock()
        mock_page_service.list_pages.return_value = ([], 0)

        app.dependency_overrides[get_page_service] = lambda: mock_page_service

        response = client.get("/api/v1/pages?status=failed")

        assert response.status_code == 200
        mock_page_service.list_pages.assert_called_once_with(
            limit=20, offset=0, sort="created_at", order="desc", status_filter="failed"
        )

    def test_update_page_url_success(self) -> None:
        mock_service = AsyncMock()
        mock_service.update_url.return_value = {
            "current_url": "https://example.com/bad%3E",
            "new_url": "https://example.com/good",
            "status": "failed",
        }
        app.dependency_overrides[get_repair_service] = lambda: mock_service

        response = client.patch(
            "/api/v1/pages/56/url",
            json={
                "current_url": "https://example.com/bad%3E",
                "new_url": "https://example.com/good",
            },
        )

        assert response.status_code == 200
        assert response.json()["status"] == "failed"
        mock_service.update_url.assert_awaited_once_with(
            56, "https://example.com/bad%3E", "https://example.com/good"
        )

    def test_update_page_url_rejects_malformed_suffix(self) -> None:
        app.dependency_overrides[get_repair_service] = lambda: AsyncMock()
        response = client.patch(
            "/api/v1/pages/56/url",
            json={
                "current_url": "https://example.com/old",
                "new_url": "https://example.com/bad%3E",
            },
        )
        assert response.status_code == 422

    def test_update_page_url_returns_conflict(self) -> None:
        mock_service = AsyncMock()
        mock_service.update_url.side_effect = FileExistsError("URL already exists")
        app.dependency_overrides[get_repair_service] = lambda: mock_service
        response = client.patch(
            "/api/v1/pages/56/url",
            json={
                "current_url": "https://example.com/old",
                "new_url": "https://example.com/new",
            },
        )
        assert response.status_code == 409

    def test_list_pending_repairs(self) -> None:
        mock_service = AsyncMock()
        mock_service.list_cases.return_value = []
        app.dependency_overrides[get_repair_service] = lambda: mock_service
        response = client.get("/api/v1/repairs?status=pending")
        assert response.status_code == 200
        assert response.json() == {"repairs": [], "total": 0}
