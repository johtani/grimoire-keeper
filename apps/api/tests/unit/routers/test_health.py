"""Tests for health router."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from grimoire_api.main import app
from grimoire_api.utils.exceptions import VectorizerError

client = TestClient(app)


class TestHealthRouter:
    """ヘルスチェックルーターテストクラス."""

    def test_health_check_returns_build_info(self) -> None:
        """ヘルスチェックがビルド情報を含むことを確認."""
        app.state.weaviate_manager = MagicMock()
        app.state.weaviate_manager.get_ready_client = AsyncMock(return_value=object())
        database = MagicMock()
        database.fetch_one = AsyncMock(return_value=(1,))
        with (
            patch(
                "grimoire_api.routers.health.get_db_connection", return_value=database
            ),
            patch("grimoire_api.routers.health.validate_weaviate_schema"),
        ):
            response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["message"] == "Grimoire Keeper API is ready"
        assert "version" in data
        assert "git_commit" in data
        assert "build_date" in data
        assert data["database"] == "ready"
        assert data["weaviate"] == "ready"

    def test_health_check_returns_503_when_weaviate_unavailable(self) -> None:
        """Weaviate未接続時はreadinessエラーを返すことを確認."""
        app.state.weaviate_manager = MagicMock()
        app.state.weaviate_manager.get_ready_client = AsyncMock(return_value=None)

        database = MagicMock()
        database.fetch_one = AsyncMock(return_value=(1,))
        with patch(
            "grimoire_api.routers.health.get_db_connection", return_value=database
        ):
            response = client.get("/api/v1/health")

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "service_unavailable"
        assert response.json()["error"]["message"] == (
            "The service is temporarily unavailable"
        )
        assert (
            response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
        )

    def test_readiness_returns_503_when_database_unavailable(self) -> None:
        """DB 障害時は Weaviate が正常でも readiness エラーになる."""
        app.state.weaviate_manager = MagicMock()
        app.state.weaviate_manager.get_ready_client = AsyncMock(return_value=object())
        database = MagicMock()
        database.fetch_one = AsyncMock(side_effect=RuntimeError("database down"))

        with (
            patch(
                "grimoire_api.routers.health.get_db_connection", return_value=database
            ),
            patch("grimoire_api.routers.health.validate_weaviate_schema"),
        ):
            response = client.get("/api/v1/health/ready")

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "service_unavailable"
        assert "database down" not in response.text

    def test_liveness_ignores_dependency_failures(self) -> None:
        """liveness は DB と Weaviate の状態を確認しない."""
        app.state.weaviate_manager = None

        with patch("grimoire_api.routers.health.get_db_connection") as database:
            response = client.get("/api/v1/health/live")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        database.assert_not_called()

    @patch("grimoire_api.routers.health.settings")
    @patch("grimoire_api.routers.health.APP_VERSION", "1.2.3")
    def test_health_check_with_build_info(self, mock_settings: object) -> None:
        """ビルド情報が環境変数から正しく反映されることを確認."""
        app.state.weaviate_manager = MagicMock()
        app.state.weaviate_manager.get_ready_client = AsyncMock(return_value=object())
        database = MagicMock()
        database.fetch_one = AsyncMock(return_value=(1,))
        mock_settings.GIT_COMMIT = "abc1234"
        mock_settings.BUILD_DATE = "2026-04-09T12:00:00Z"

        with (
            patch(
                "grimoire_api.routers.health.get_db_connection", return_value=database
            ),
            patch("grimoire_api.routers.health.validate_weaviate_schema"),
        ):
            response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "1.2.3"
        assert data["git_commit"] == "abc1234"
        assert data["build_date"] == "2026-04-09T12:00:00Z"

    def test_readiness_returns_schema_diagnostics(self, caplog: object) -> None:
        """schema 不一致はログと503 detailsから診断できる."""
        app.state.weaviate_manager = MagicMock()
        app.state.weaviate_manager.get_ready_client = AsyncMock(return_value=object())
        database = MagicMock()
        database.fetch_one = AsyncMock(return_value=(1,))
        schema_error = (
            "Incompatible Weaviate schema for GrimoirePage: "
            "required property 'pageId' is missing"
        )

        with (
            patch(
                "grimoire_api.routers.health.get_db_connection", return_value=database
            ),
            patch(
                "grimoire_api.routers.health.validate_weaviate_schema",
                side_effect=VectorizerError(schema_error),
            ),
        ):
            response = client.get("/api/v1/health/ready")

        assert response.status_code == 503
        assert response.json()["error"]["details"] == [
            {
                "dependency": "weaviate",
                "reason": "schema_incompatible",
                "message": schema_error,
            }
        ]
        assert schema_error in caplog.text

    def test_readiness_hides_unexpected_schema_check_error(self) -> None:
        """schema 取得障害は内部メッセージを公開せず503にする."""
        app.state.weaviate_manager = MagicMock()
        app.state.weaviate_manager.get_ready_client = AsyncMock(return_value=object())
        database = MagicMock()
        database.fetch_one = AsyncMock(return_value=(1,))

        with (
            patch(
                "grimoire_api.routers.health.get_db_connection", return_value=database
            ),
            patch(
                "grimoire_api.routers.health.validate_weaviate_schema",
                side_effect=RuntimeError("secret SDK failure"),
            ),
        ):
            response = client.get("/api/v1/health/ready")

        assert response.status_code == 503
        assert response.json()["error"]["details"] == [
            {
                "dependency": "weaviate",
                "reason": "schema_check_failed",
                "message": "Weaviate schema could not be inspected",
            }
        ]
        assert "secret SDK failure" not in response.text
