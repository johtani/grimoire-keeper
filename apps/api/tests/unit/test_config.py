"""Application settings validation tests."""

import pytest
from grimoire_api.config import Settings


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
    assert make_settings().missing_required_vars() == []


def test_cloud_llm_accepts_real_api_key() -> None:
    """クラウドLLMでは実APIキーを許可する."""
    settings = make_settings(LLM_API_BASE="", LLM_API_KEY="provider-key")

    assert settings.missing_required_vars() == []


@pytest.mark.parametrize("llm_api_key", ["", " ", "dummy", " DUMMY "])
def test_cloud_llm_rejects_missing_or_dummy_api_key(llm_api_key: str) -> None:
    """クラウドLLMでは空値とdummyキーを拒否する."""
    settings = make_settings(LLM_API_BASE="", LLM_API_KEY=llm_api_key)

    assert settings.missing_required_vars() == ["LLM_API_KEY"]
    with pytest.raises(SystemExit, match="1"):
        settings.validate_required_vars()


def test_existing_required_api_keys_remain_required() -> None:
    """Jinaと埋め込み用OpenAIキーの必須検証を維持する."""
    settings = make_settings(JINA_API_KEY="", OPENAI_API_KEY=" ")

    assert settings.missing_required_vars() == ["JINA_API_KEY", "OPENAI_API_KEY"]
