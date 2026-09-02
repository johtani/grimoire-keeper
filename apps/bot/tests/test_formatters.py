"""フォーマッターのテスト"""

import pytest
from grimoire_bot.models.api import ProcessStatusResponse
from grimoire_bot.services.api_client import ApiClientError
from grimoire_bot.utils.formatters import (
    format_error_message,
    format_process_status,
)


@pytest.mark.parametrize(
    ("fixture_name", "expected_emoji"),
    [
        ("process_status_queued.json", "⏸️ queued"),
        ("process_status_processing.json", "⏳ processing"),
        ("process_status_completed.json", "✅ completed"),
        ("process_status_failed.json", "❌ failed"),
    ],
)
def test_format_process_status(bot_contract_fixture, fixture_name, expected_emoji):
    """ネストされた API 契約の4状態をフォーマットする."""
    result = ProcessStatusResponse.model_validate(bot_contract_fixture(fixture_name))

    formatted = format_process_status(result, result.page.id)

    assert "📊 処理状況" in formatted
    assert f"ID: {result.page.id}" in formatted
    assert result.page.url in formatted
    assert result.page.title in formatted
    assert expected_emoji in formatted


def test_format_error_message():
    """エラーメッセージフォーマットテスト"""
    formatted = format_error_message(
        ApiClientError("service_unavailable", "request-1234"), "URL処理"
    )

    assert "❌ エラーが発生しました" in formatted
    assert "操作: URL処理" in formatted
    assert "詳細: サービスを一時的に利用できません。" in formatted
    assert "リクエストID: request-1234" in formatted
    assert "管理者にお問い合わせ" in formatted


def test_format_error_message_does_not_expose_unknown_exception() -> None:
    formatted = format_error_message(RuntimeError("secret database URL"))

    assert "secret database URL" not in formatted
    assert "操作に失敗しました。" in formatted
