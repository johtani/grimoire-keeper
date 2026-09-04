"""Application settings validation tests."""

import pytest
from grimoire_api.config import Settings
from pydantic import ValidationError


def make_settings(**overrides: str) -> Settings:
    """必須値を設定した、環境から独立したSettingsを作る."""
    values = {
        "JINA_API_KEY": "jina-key",
        "OPENAI_API_KEY": "embedding-key",
        "LLM_API_BASE": "http://localhost:8080/v1",
        "LLM_API_KEY": "dummy",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def test_local_llm_allows_dummy_api_key() -> None:
    """ローカル互換APIではdummyキーを許可する."""
    assert make_settings().missing_worker_required_vars() == []


def test_cloud_llm_accepts_real_api_key() -> None:
    """クラウドLLMでは実APIキーを許可する."""
    settings = make_settings(LLM_API_BASE="", LLM_API_KEY="provider-key")

    assert settings.missing_worker_required_vars() == []


@pytest.mark.parametrize("llm_api_key", ["", " ", "dummy", " DUMMY "])
def test_cloud_llm_rejects_missing_or_dummy_api_key(llm_api_key: str) -> None:
    """クラウドLLMでは空値とdummyキーを拒否する."""
    settings = make_settings(LLM_API_BASE="", LLM_API_KEY=llm_api_key)

    assert settings.missing_worker_required_vars() == ["LLM_API_KEY"]
    with pytest.raises(SystemExit, match="1"):
        settings.validate_worker_required_vars()


def test_existing_required_api_keys_remain_required() -> None:
    """Jinaと埋め込み用OpenAIキーの必須検証を維持する."""
    settings = make_settings(JINA_API_KEY="", OPENAI_API_KEY=" ")

    assert settings.missing_worker_required_vars() == [
        "JINA_API_KEY",
        "OPENAI_API_KEY",
    ]


def test_api_does_not_require_worker_credentials() -> None:
    """SQLite APIはJina・LLM・埋め込みキーなしで起動できる."""
    settings = make_settings(
        JINA_API_KEY="", OPENAI_API_KEY="", LLM_API_BASE="", LLM_API_KEY=""
    )

    assert settings.missing_api_required_vars() == []
    settings.validate_api_required_vars()


def test_api_requires_database_path() -> None:
    settings = make_settings(DATABASE_PATH=" ")

    assert settings.missing_api_required_vars() == ["DATABASE_PATH"]
    with pytest.raises(SystemExit, match="1"):
        settings.validate_api_required_vars()


def test_embedding_defaults_are_pinned() -> None:
    settings = make_settings()

    assert settings.WEAVIATE_EMBEDDING_PROVIDER == "text2vec-openai"
    assert settings.WEAVIATE_EMBEDDING_MODEL == "text-embedding-ada-002"
    assert settings.WEAVIATE_EMBEDDING_DIMENSIONS == 1536


def test_retry_policy_defaults_are_bounded() -> None:
    settings = make_settings()

    assert settings.JINA_RETRY_ATTEMPTS == 3
    assert settings.LLM_RETRY_ATTEMPTS == 3
    assert settings.WEAVIATE_RETRY_ATTEMPTS == 3
    assert settings.JINA_CONNECT_TIMEOUT == 5.0
    assert settings.WEAVIATE_INSERT_TIMEOUT == 90.0


def test_retry_backoff_cap_cannot_be_below_base() -> None:
    with pytest.raises(ValueError, match="JINA_RETRY_BACKOFF_MAX"):
        make_settings(JINA_RETRY_BACKOFF_BASE=2, JINA_RETRY_BACKOFF_MAX=1)


@pytest.mark.parametrize(
    ("model", "dimensions"),
    [
        ("text-embedding-ada-002", 1024),
        ("text-embedding-3-small", 1537),
        ("text-embedding-3-large", 3073),
    ],
)
def test_embedding_rejects_incompatible_dimensions(model: str, dimensions: int) -> None:
    with pytest.raises(ValidationError):
        make_settings(
            WEAVIATE_EMBEDDING_MODEL=model,
            WEAVIATE_EMBEDDING_DIMENSIONS=dimensions,
        )


def test_embedding_accepts_reduced_dimensions_for_v3_models() -> None:
    settings = make_settings(
        WEAVIATE_EMBEDDING_MODEL="text-embedding-3-large",
        WEAVIATE_EMBEDDING_DIMENSIONS=1024,
    )

    assert settings.WEAVIATE_EMBEDDING_DIMENSIONS == 1024
