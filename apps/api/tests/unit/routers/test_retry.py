"""Tests for retry router."""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from grimoire_api.dependencies import get_retry_service
from grimoire_api.main import app
from grimoire_api.utils.exceptions import (
    ResourceConflictError,
    ResourceNotFoundError,
)

client = TestClient(app)


class TestRetryRouter:
    """再処理ルーターテストクラス."""

    def test_retry_single_page_success(self) -> None:
        """個別ページ再処理成功のテスト."""
        mock_service = AsyncMock()
        mock_service.retry_single_page.return_value = {
            "status": "retry_started",
            "page_id": 1,
            "job_id": 10,
            "restart_from": "download",
            "message": "Retry processing started",
        }
        app.dependency_overrides[get_retry_service] = lambda: mock_service

        response = client.post("/api/v1/retry/1")

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "retry_started"
        assert data["page_id"] == 1
        assert data["restart_from"] == "download"
        mock_service.retry_single_page.assert_called_once_with(1)

    def test_retry_single_page_error(self) -> None:
        """個別ページ再処理エラーのテスト."""
        mock_service = AsyncMock()
        mock_service.retry_single_page.side_effect = Exception("retry failed")
        app.dependency_overrides[get_retry_service] = lambda: mock_service

        response = client.post("/api/v1/retry/1")

        assert response.status_code == 500

    @pytest.mark.parametrize(
        ("path", "service_method", "error", "status_code", "code"),
        [
            (
                "/api/v1/retry/999",
                "retry_single_page",
                ResourceNotFoundError("Page 999 not found"),
                404,
                "not_found",
            ),
            (
                "/api/v1/reprocess/999",
                "reprocess_page",
                ResourceNotFoundError("Page 999 not found"),
                404,
                "not_found",
            ),
            (
                "/api/v1/retry/999",
                "retry_single_page",
                ResourceConflictError("An active job already exists"),
                409,
                "conflict",
            ),
        ],
    )
    def test_page_operation_domain_errors(
        self,
        path: str,
        service_method: str,
        error: Exception,
        status_code: int,
        code: str,
    ) -> None:
        mock_service = AsyncMock()
        getattr(mock_service, service_method).side_effect = error
        app.dependency_overrides[get_retry_service] = lambda: mock_service

        response = client.post(path)

        assert response.status_code == status_code
        assert response.json()["error"] == {"code": code, "message": str(error)}

    def test_reprocess_page_success(self) -> None:
        """ページ再処理成功のテスト."""
        mock_service = AsyncMock()
        mock_service.reprocess_page.return_value = {
            "status": "reprocess_started",
            "page_id": 2,
            "job_id": 20,
            "restart_from": "llm",
            "message": "Reprocessing started",
        }
        app.dependency_overrides[get_retry_service] = lambda: mock_service

        response = client.post(
            "/api/v1/reprocess/2",
            json={"from_step": "llm"},
        )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "reprocess_started"
        mock_service.reprocess_page.assert_called_once_with(2, "llm")

    def test_reprocess_page_default_step(self) -> None:
        """from_step 未指定時のデフォルト値テスト."""
        mock_service = AsyncMock()
        mock_service.reprocess_page.return_value = {
            "status": "reprocess_started",
            "page_id": 3,
            "job_id": 30,
            "restart_from": "vectorize",
            "message": "Reprocessing started",
        }
        app.dependency_overrides[get_retry_service] = lambda: mock_service

        response = client.post("/api/v1/reprocess/3")

        assert response.status_code == 202
        mock_service.reprocess_page.assert_called_once_with(3, "auto")

    def test_retry_all_failed_success(self) -> None:
        """全失敗ページ再処理成功のテスト."""
        mock_service = AsyncMock()
        mock_service.retry_all_failed.return_value = {
            "status": "batch_retry_started",
            "total_failed_pages": 3,
            "retry_count": 3,
            "job_ids": [10, 11, 12],
            "message": "Batch retry started",
        }
        app.dependency_overrides[get_retry_service] = lambda: mock_service

        response = client.post("/api/v1/retry-failed")

        assert response.status_code == 202
        data = response.json()
        assert data["total_failed_pages"] == 3
        assert data["retry_count"] == 3

    def test_retry_all_failed_with_params(self) -> None:
        """パラメータ付き全失敗ページ再処理のテスト."""
        mock_service = AsyncMock()
        mock_service.retry_all_failed.return_value = {
            "status": "batch_retry_started",
            "total_failed_pages": 1,
            "retry_count": 1,
            "job_ids": [10],
            "message": "Batch retry started",
        }
        app.dependency_overrides[get_retry_service] = lambda: mock_service

        response = client.post(
            "/api/v1/retry-failed",
            json={"max_retries": 5},
        )

        assert response.status_code == 202
        mock_service.retry_all_failed.assert_called_once_with(max_retries=5)

    @pytest.mark.parametrize("max_retries", [1, 1000])
    def test_retry_all_failed_accepts_boundaries(self, max_retries: int) -> None:
        """一括再処理件数の境界値を受理する."""
        mock_service = AsyncMock()
        mock_service.retry_all_failed.return_value = {
            "status": "no_failed_pages",
            "total_failed_pages": 0,
            "retry_count": 0,
            "message": "No failed pages found",
        }
        app.dependency_overrides[get_retry_service] = lambda: mock_service

        response = client.post(
            "/api/v1/retry-failed", json={"max_retries": max_retries}
        )

        assert response.status_code == 202

    @pytest.mark.parametrize(
        "payload",
        [
            {"max_retries": 0},
            {"max_retries": -1},
            {"max_retries": 1001},
            {"delay_seconds": 1},
            {"unknown": True},
        ],
    )
    def test_retry_all_failed_rejects_invalid_request(
        self, payload: dict[str, object]
    ) -> None:
        """制約違反や廃止済みフィールドを 422 にする."""
        app.dependency_overrides[get_retry_service] = lambda: AsyncMock()

        response = client.post("/api/v1/retry-failed", json=payload)

        assert response.status_code == 422

    def test_reprocess_rejects_unknown_step(self) -> None:
        """未知の from_step は Pydantic により 422 になる."""
        app.dependency_overrides[get_retry_service] = lambda: AsyncMock()
        response = client.post("/api/v1/reprocess/2", json={"from_step": "unknown"})

        assert response.status_code == 422

    @pytest.mark.parametrize("path", ["/api/v1/retry/0", "/api/v1/reprocess/-1"])
    def test_page_operations_reject_invalid_page_id(self, path: str) -> None:
        response = client.post(path)

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"
