"""Tests for retry router."""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from grimoire_api.dependencies import get_retry_service
from grimoire_api.main import app

client = TestClient(app)


class TestRetryRouter:
    """再処理ルーターテストクラス."""

    def setup_method(self) -> None:
        """各テスト前に dependency_overrides をクリア."""
        app.dependency_overrides.clear()

    def teardown_method(self) -> None:
        """各テスト後に dependency_overrides をクリア."""
        app.dependency_overrides.clear()

    def test_retry_single_page_success(self) -> None:
        """個別ページ再処理成功のテスト."""
        mock_service = AsyncMock()
        mock_service.retry_single_page.return_value = {
            "status": "success",
            "page_id": 1,
        }
        app.dependency_overrides[get_retry_service] = lambda: mock_service

        response = client.post("/api/v1/retry/1")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["page_id"] == 1
        mock_service.retry_single_page.assert_called_once_with(1)

    def test_retry_single_page_error(self) -> None:
        """個別ページ再処理エラーのテスト."""
        mock_service = AsyncMock()
        mock_service.retry_single_page.side_effect = Exception("retry failed")
        app.dependency_overrides[get_retry_service] = lambda: mock_service

        response = client.post("/api/v1/retry/1")

        assert response.status_code == 500

    def test_reprocess_page_success(self) -> None:
        """ページ再処理成功のテスト."""
        mock_service = AsyncMock()
        mock_service.reprocess_page.return_value = {
            "status": "success",
            "page_id": 2,
        }
        app.dependency_overrides[get_retry_service] = lambda: mock_service

        response = client.post(
            "/api/v1/reprocess/2",
            json={"from_step": "llm"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        mock_service.reprocess_page.assert_called_once_with(2, "llm")

    def test_reprocess_page_default_step(self) -> None:
        """from_step 未指定時のデフォルト値テスト."""
        mock_service = AsyncMock()
        mock_service.reprocess_page.return_value = {"status": "success", "page_id": 3}
        app.dependency_overrides[get_retry_service] = lambda: mock_service

        response = client.post("/api/v1/reprocess/3")

        assert response.status_code == 200
        mock_service.reprocess_page.assert_called_once_with(3, "auto")

    def test_retry_all_failed_success(self) -> None:
        """全失敗ページ再処理成功のテスト."""
        mock_service = AsyncMock()
        mock_service.retry_all_failed.return_value = {
            "total": 3,
            "success": 3,
            "failed": 0,
        }
        app.dependency_overrides[get_retry_service] = lambda: mock_service

        response = client.post("/api/v1/retry-failed")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert data["success"] == 3

    def test_retry_all_failed_with_params(self) -> None:
        """パラメータ付き全失敗ページ再処理のテスト."""
        mock_service = AsyncMock()
        mock_service.retry_all_failed.return_value = {
            "total": 1,
            "success": 1,
            "failed": 0,
        }
        app.dependency_overrides[get_retry_service] = lambda: mock_service

        response = client.post(
            "/api/v1/retry-failed",
            json={"max_retries": 5, "delay_seconds": 2},
        )

        assert response.status_code == 200
        mock_service.retry_all_failed.assert_called_once_with(
            max_retries=5, delay_seconds=2
        )
