"""Application lifespan tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from grimoire_api.main import app, lifespan


@pytest.mark.asyncio
async def test_lifespan_starts_and_stops_manager_after_database_init() -> None:
    """DB 初期化成功後に Weaviate manager を起動・停止する."""
    manager = MagicMock()
    manager.start = AsyncMock()
    manager.stop = AsyncMock()
    jina_client = MagicMock()
    jina_client.close = AsyncMock()

    with (
        patch(
            "grimoire_api.main.ensure_database_initialized", new=AsyncMock()
        ) as initialize,
        patch("grimoire_api.main.WeaviateConnectionManager", return_value=manager),
        patch("grimoire_api.main.get_jina_client", return_value=jina_client),
    ):
        async with lifespan(app):
            manager.start.assert_awaited_once()
            assert not hasattr(app.state, "job_worker")

    initialize.assert_awaited_once()
    manager.stop.assert_awaited_once()
    jina_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifespan_does_not_start_manager_when_database_init_fails() -> None:
    """DB 初期化失敗時は Weaviate manager や worker の起動に進まない."""
    manager_class = MagicMock()

    with (
        patch(
            "grimoire_api.main.ensure_database_initialized",
            new=AsyncMock(side_effect=RuntimeError("database init failed")),
        ),
        patch("grimoire_api.main.WeaviateConnectionManager", manager_class),
    ):
        with pytest.raises(RuntimeError, match="database init failed"):
            async with lifespan(app):
                pytest.fail("lifespan must not start")

    manager_class.assert_not_called()


def test_same_origin_request_succeeds_without_cors_headers() -> None:
    """同一オリジンで利用する通常のAPIリクエストはCORSヘッダーなしで成功する."""
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "Grimoire Keeper API is running"}
    assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-credentials" not in response.headers


def test_cross_origin_request_is_not_allowed() -> None:
    """外部オリジンにはCORS許可ヘッダーを返さない."""
    response = TestClient(app).get("/", headers={"Origin": "https://external.example"})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-credentials" not in response.headers


def test_cross_origin_preflight_is_not_allowed() -> None:
    """外部オリジンのpreflightをCORSリクエストとして許可しない."""
    response = TestClient(app).options(
        "/api/v1/search",
        headers={
            "Origin": "https://external.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )

    assert response.status_code == 405
    assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-methods" not in response.headers
    assert "access-control-allow-headers" not in response.headers
    assert "access-control-allow-credentials" not in response.headers
