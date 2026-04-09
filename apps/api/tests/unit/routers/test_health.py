"""Tests for health router."""

from unittest.mock import patch

from fastapi.testclient import TestClient
from grimoire_api.main import app

client = TestClient(app)


class TestHealthRouter:
    """ヘルスチェックルーターテストクラス."""

    def test_health_check_returns_build_info(self) -> None:
        """ヘルスチェックがビルド情報を含むことを確認."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["message"] == "Grimoire Keeper API is running"
        assert "version" in data
        assert "git_commit" in data
        assert "build_date" in data

    @patch("grimoire_api.routers.health.settings")
    @patch("grimoire_api.routers.health.APP_VERSION", "1.2.3")
    def test_health_check_with_build_info(self, mock_settings: object) -> None:
        """ビルド情報が環境変数から正しく反映されることを確認."""
        mock_settings.GIT_COMMIT = "abc1234"
        mock_settings.BUILD_DATE = "2026-04-09T12:00:00Z"

        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "1.2.3"
        assert data["git_commit"] == "abc1234"
        assert data["build_date"] == "2026-04-09T12:00:00Z"
