"""Tests for the public system information endpoint."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from grimoire_api.config import settings
from grimoire_api.main import app

client = TestClient(app)


def _config(vectors: dict[str, tuple[object, dict[str, object]]]) -> object:
    vector_config = {
        name: SimpleNamespace(
            vectorizer=SimpleNamespace(vectorizer=vectorizer, model=model)
        )
        for name, (vectorizer, model) in vectors.items()
    }
    return SimpleNamespace(vector_config=vector_config)


def _ready_manager(page_config: object, chunk_config: object) -> MagicMock:
    weaviate_client = MagicMock()
    configs = {
        settings.WEAVIATE_PAGE_COLLECTION_NAME: page_config,
        settings.WEAVIATE_CHUNK_COLLECTION_NAME: chunk_config,
    }
    weaviate_client.collections.get.side_effect = lambda name: SimpleNamespace(
        config=SimpleNamespace(get=lambda: configs[name])
    )
    manager = MagicMock()
    manager.get_ready_client = AsyncMock(return_value=weaviate_client)
    return manager


def test_system_info_returns_services_and_live_named_vectors() -> None:
    """Configured LLM and live named-vector models are returned."""
    page_config = _config(
        {
            "title_vector": (
                "text2vec-openai",
                {
                    "model": "text-embedding-3-small",
                    "baseURL": "https://private-vectorizer.example",
                },
            ),
            "memo_vector": ("text2vec-openai", {}),
        }
    )
    chunk_config = _config({"content_vector": ("text2vec-openai", {"model": "ada"})})
    app.state.weaviate_manager = _ready_manager(page_config, chunk_config)

    with patch("grimoire_api.routers.system_info.settings.LLM_MODEL", "test/model"):
        response = client.get("/api/v1/system-info")

    assert response.status_code == 200
    data = response.json()
    assert [service["name"] for service in data["services"]] == [
        "Jina AI Reader",
        "LiteLLM",
        "Weaviate",
    ]
    assert data["services"][1]["model"] == "test/model"
    assert "private-vectorizer" not in response.text
    assert data["weaviate"]["status"] == "available"
    assert data["weaviate"]["collections"] == [
        {
            "name": settings.WEAVIATE_PAGE_COLLECTION_NAME,
            "vectors": [
                {
                    "name": "title_vector",
                    "vectorizer": "text2vec-openai",
                    "model": {"model": "text-embedding-3-small"},
                    "uses_module_default": False,
                },
                {
                    "name": "memo_vector",
                    "vectorizer": "text2vec-openai",
                    "model": {},
                    "uses_module_default": True,
                },
            ],
        },
        {
            "name": settings.WEAVIATE_CHUNK_COLLECTION_NAME,
            "vectors": [
                {
                    "name": "content_vector",
                    "vectorizer": "text2vec-openai",
                    "model": {"model": "ada"},
                    "uses_module_default": False,
                }
            ],
        },
    ]


def test_system_info_returns_partial_information_when_weaviate_unavailable() -> None:
    """An unavailable client does not hide the static service information."""
    manager = MagicMock()
    manager.get_ready_client = AsyncMock(return_value=None)
    app.state.weaviate_manager = manager

    response = client.get("/api/v1/system-info")

    assert response.status_code == 200
    assert response.json()["services"]
    assert response.json()["weaviate"] == {
        "status": "unavailable",
        "message": "Weaviate is unavailable",
        "collections": [],
    }


def test_system_info_handles_schema_failure_without_exposing_details() -> None:
    """Missing collections and SDK errors produce a safe public response."""
    weaviate_client = MagicMock()
    weaviate_client.collections.get.side_effect = RuntimeError(
        "secret-host:8080 api-key-value"
    )
    manager = MagicMock()
    manager.get_ready_client = AsyncMock(return_value=weaviate_client)
    app.state.weaviate_manager = manager

    response = client.get("/api/v1/system-info")

    assert response.status_code == 200
    body = response.text
    assert response.json()["weaviate"] == {
        "status": "unavailable",
        "message": "Weaviate schema is unavailable",
        "collections": [],
    }
    assert "secret-host" not in body
    assert "api-key-value" not in body


def test_system_info_does_not_publish_secret_settings() -> None:
    """API keys and internal connection details are never serialized."""
    app.state.weaviate_manager = None
    with (
        patch("grimoire_api.routers.system_info.settings.JINA_API_KEY", "jina-secret"),
        patch(
            "grimoire_api.routers.system_info.settings.OPENAI_API_KEY",
            "openai-secret",
        ),
        patch("grimoire_api.routers.system_info.settings.LLM_API_BASE", "internal-url"),
        patch("grimoire_api.routers.system_info.settings.WEAVIATE_HOST", "secret-host"),
    ):
        body = client.get("/api/v1/system-info").text

    assert "jina-secret" not in body
    assert "openai-secret" not in body
    assert "internal-url" not in body
    assert "secret-host" not in body
