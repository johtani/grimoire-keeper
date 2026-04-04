"""Tests for process router."""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from grimoire_api.dependencies import get_url_processor_service
from grimoire_api.main import app

client = TestClient(app)


class TestProcessRouter:
    """URL処理ルーターテストクラス."""

    def test_process_url_new(self) -> None:
        """新規URL処理リクエストのテスト."""
        mock_processor = AsyncMock()
        mock_processor.prepare_url_processing.return_value = {
            "status": "prepared",
            "page_id": 1,
            "log_id": 10,
            "message": "Processing prepared",
        }
        app.dependency_overrides[get_url_processor_service] = lambda: mock_processor

        response = client.post(
            "/api/v1/process-url",
            json={"url": "https://example.com"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processing"
        assert data["page_id"] == 1

    def test_process_url_already_exists(self) -> None:
        """既存URLの重複リクエストのテスト."""
        mock_processor = AsyncMock()
        mock_processor.prepare_url_processing.return_value = {
            "status": "already_exists",
            "page_id": 42,
            "message": "URL already exists in the database",
        }
        app.dependency_overrides[get_url_processor_service] = lambda: mock_processor

        response = client.post(
            "/api/v1/process-url",
            json={"url": "https://example.com"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "already_exists"
        assert data["page_id"] == 42

    def test_process_url_with_memo(self) -> None:
        """メモ付きURL処理リクエストのテスト."""
        mock_processor = AsyncMock()
        mock_processor.prepare_url_processing.return_value = {
            "status": "prepared",
            "page_id": 2,
            "log_id": 20,
            "message": "Processing prepared",
        }
        app.dependency_overrides[get_url_processor_service] = lambda: mock_processor

        response = client.post(
            "/api/v1/process-url",
            json={"url": "https://example.com", "memo": "test memo"},
        )

        assert response.status_code == 200
        mock_processor.prepare_url_processing.assert_called_once_with(
            "https://example.com/", "test memo"
        )

    def test_process_url_error(self) -> None:
        """URL処理エラー時のテスト."""
        mock_processor = AsyncMock()
        mock_processor.prepare_url_processing.side_effect = Exception(
            "processing error"
        )
        app.dependency_overrides[get_url_processor_service] = lambda: mock_processor

        response = client.post(
            "/api/v1/process-url",
            json={"url": "https://example.com"},
        )

        assert response.status_code == 500

    def test_get_process_status(self) -> None:
        """処理状況取得のテスト."""
        mock_processor = AsyncMock()
        mock_processor.get_processing_status.return_value = {
            "page_id": 1,
            "status": "completed",
            "last_success_step": "completed",
        }
        app.dependency_overrides[get_url_processor_service] = lambda: mock_processor

        response = client.get("/api/v1/process-status/1")

        assert response.status_code == 200
        data = response.json()
        assert data["page_id"] == 1
        assert data["status"] == "completed"
