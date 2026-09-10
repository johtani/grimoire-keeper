"""Integration tests for API routing and public response contracts."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from grimoire_api.dependencies import get_search_service
from grimoire_api.main import app
from grimoire_api.models.response import SearchResult


def test_root_endpoint(integration_client: TestClient) -> None:
    response = integration_client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "Grimoire Keeper API is running"}


def test_liveness_endpoint(integration_client: TestClient) -> None:
    response = integration_client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_search_endpoint_serializes_service_results(
    integration_client: TestClient,
) -> None:
    search_service = AsyncMock()
    search_service.vector_search.return_value = [
        SearchResult(
            page_id=1,
            chunk_id=0,
            url="https://example.com",
            title="Test Title",
            memo="Test memo",
            content="Test content",
            summary="Test summary",
            keywords=["test", "keyword"],
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
            score=0.9,
        )
    ]
    app.dependency_overrides[get_search_service] = lambda: search_service

    response = integration_client.post(
        "/api/v1/search", json={"query": "test query", "limit": 5}
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    search_service.vector_search.assert_awaited_once()


def test_process_url_rejects_invalid_url(integration_client: TestClient) -> None:
    response = integration_client.post(
        "/api/v1/process-url", json={"url": "invalid-url", "memo": "Test memo"}
    )

    assert response.status_code == 422


def test_search_rejects_missing_query(integration_client: TestClient) -> None:
    app.dependency_overrides[get_search_service] = lambda: AsyncMock()
    response = integration_client.post("/api/v1/search", json={"limit": 5})

    assert response.status_code == 422
