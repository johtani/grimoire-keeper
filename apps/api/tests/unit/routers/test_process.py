"""Tests for process router."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from grimoire_api.dependencies import (
    get_page_repository,
    get_url_processor_service,
    get_weaviate_client,
)
from grimoire_api.main import app
from grimoire_api.models.database import PageStatus
from grimoire_api.utils.exceptions import ResourceNotFoundError

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
            "job_id": 100,
            "message": "Processing prepared",
        }
        app.dependency_overrides[get_url_processor_service] = lambda: mock_processor

        with (
            patch(
                "grimoire_api.routers.process.url_processing_api_requests"
            ) as requests,
            patch(
                "grimoire_api.routers.process.url_processing_api_duration"
            ) as duration,
        ):
            response = client.post(
                "/api/v1/process-url",
                json={"url": "https://example.com"},
            )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "queued"
        assert data["job_id"] == 100
        assert data["page_id"] == 1
        requests.add.assert_called_once_with(
            1, {"outcome": "queued", "has_memo": False}
        )
        assert duration.record.call_count == 1
        assert duration.record.call_args.args[1] == {
            "outcome": "queued",
            "has_memo": False,
        }

    def test_process_url_already_exists(self) -> None:
        """既存URLの重複リクエストのテスト."""
        mock_processor = AsyncMock()
        mock_processor.prepare_url_processing.return_value = {
            "status": "already_exists",
            "page_id": 42,
            "message": "URL already exists in the database",
        }
        app.dependency_overrides[get_url_processor_service] = lambda: mock_processor

        with patch(
            "grimoire_api.routers.process.url_processing_api_requests"
        ) as requests:
            response = client.post(
                "/api/v1/process-url",
                json={"url": "https://example.com"},
            )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "already_exists"
        assert data["page_id"] == 42
        requests.add.assert_called_once_with(
            1, {"outcome": "duplicate", "has_memo": False}
        )

    def test_process_url_with_memo(self) -> None:
        """メモ付きURL処理リクエストのテスト."""
        mock_processor = AsyncMock()
        mock_processor.prepare_url_processing.return_value = {
            "status": "prepared",
            "page_id": 2,
            "log_id": 20,
            "job_id": 200,
            "message": "Processing prepared",
        }
        app.dependency_overrides[get_url_processor_service] = lambda: mock_processor

        response = client.post(
            "/api/v1/process-url",
            json={"url": "https://example.com", "memo": "test memo"},
        )

        assert response.status_code == 202
        mock_processor.prepare_url_processing.assert_called_once_with(
            "https://example.com/", "test memo"
        )

    def test_process_url_rejects_unused_slack_fields(self) -> None:
        """未使用の Slack 固有フィールドを拒否する."""
        app.dependency_overrides[get_weaviate_client] = lambda: object()

        for field in ("slack_channel", "slack_user"):
            response = client.post(
                "/api/v1/process-url",
                json={"url": "https://example.com", field: "unused"},
            )

            assert response.status_code == 422
            detail = response.json()["detail"]
            assert detail[0]["type"] == "extra_forbidden"
            assert detail[0]["loc"] == ["body", field]

    def test_process_url_rejects_raw_slack_suffix(self) -> None:
        """末尾に Slack の閉じ山括弧がある URL を拒否する."""
        app.dependency_overrides[get_weaviate_client] = lambda: object()
        response = client.post(
            "/api/v1/process-url",
            json={"url": "https://example.com/article>"},
        )

        assert response.status_code == 422
        assert "detail" in response.json()
        assert "error" not in response.json()

    def test_process_url_rejects_encoded_slack_suffix(self) -> None:
        """末尾のエンコード済み閉じ山括弧も拒否する."""
        app.dependency_overrides[get_weaviate_client] = lambda: object()
        response = client.post(
            "/api/v1/process-url",
            json={"url": "https://example.com/article%3E"},
        )

        assert response.status_code == 422

    def test_process_url_does_not_resolve_weaviate_dependency(self) -> None:
        """Weaviate未接続でもSQLiteへのURL登録を受け付ける."""
        page_repo = AsyncMock()
        page_repo.get_page_by_url.return_value = None
        page_repo.create_page_with_initial_job.return_value = (1, 10, 100)
        app.dependency_overrides[get_page_repository] = lambda: page_repo

        def raise_503() -> None:
            raise HTTPException(status_code=503, detail="Weaviate is not available")

        app.dependency_overrides[get_weaviate_client] = raise_503

        response = client.post(
            "/api/v1/process-url",
            json={"url": "https://example.com"},
        )

        assert response.status_code == 202
        assert response.json()["status"] == "queued"
        page_repo.create_page_with_initial_job.assert_awaited_once()

    def test_process_url_error(self) -> None:
        """URL処理エラー時のテスト."""
        mock_processor = AsyncMock()
        mock_processor.prepare_url_processing.side_effect = Exception(
            "processing error"
        )
        app.dependency_overrides[get_url_processor_service] = lambda: mock_processor

        with patch(
            "grimoire_api.routers.process.url_processing_api_requests"
        ) as requests:
            response = client.post(
                "/api/v1/process-url",
                json={"url": "https://example.com"},
            )

        assert response.status_code == 500
        requests.add.assert_called_once_with(
            1, {"outcome": "failed", "has_memo": False}
        )

    def test_get_process_status(self) -> None:
        """処理状況取得のテスト."""
        mock_processor = AsyncMock()
        mock_processor.get_processing_status.return_value = {
            "status": "completed",
            "message": "Processing status retrieved",
            "page": {
                "id": 1,
                "url": "https://example.com",
                "title": "Example",
                "memo": None,
                "summary": "Summary",
                "keywords": ["example"],
                "created_at": "2025-01-01T12:00:00+00:00",
            },
        }
        app.dependency_overrides[get_url_processor_service] = lambda: mock_processor

        response = client.get("/api/v1/process-status/1")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["page"]["id"] == 1
        assert data["page"]["created_at"] == "2025-01-01T12:00:00Z"

    def test_process_status_does_not_resolve_weaviate_dependency(self) -> None:
        """Weaviate未接続でもSQLiteから状態を取得する."""
        page = MagicMock(
            id=1,
            url="https://example.com",
            title="Example",
            memo=None,
            summary=None,
            keywords=[],
            created_at=datetime(2025, 1, 1, tzinfo=UTC),
            status=PageStatus.QUEUED,
        )
        page_repo = AsyncMock()
        page_repo.get_page.return_value = page
        app.dependency_overrides[get_page_repository] = lambda: page_repo

        def raise_503() -> None:
            raise HTTPException(status_code=503, detail="Weaviate is not available")

        app.dependency_overrides[get_weaviate_client] = raise_503

        response = client.get("/api/v1/process-status/1")

        assert response.status_code == 200
        assert response.json()["status"] == "queued"
        page_repo.get_page.assert_awaited_once_with(1)

    def test_get_process_status_not_found(self) -> None:
        mock_processor = AsyncMock()
        mock_processor.get_processing_status.side_effect = ResourceNotFoundError(
            "Page 999 not found"
        )
        app.dependency_overrides[get_url_processor_service] = lambda: mock_processor

        response = client.get("/api/v1/process-status/999")

        assert response.status_code == 404
        assert response.json() == {
            "error": {"code": "not_found", "message": "Page 999 not found"}
        }

    def test_get_process_status_rejects_invalid_page_id(self) -> None:
        response = client.get("/api/v1/process-status/0")

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"
