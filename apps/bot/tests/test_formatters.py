"""フォーマッターのテスト"""

from grimoire_bot.services.api_client import ApiClientError
from grimoire_bot.utils.formatters import (
    format_error_message,
    format_process_status,
)


def test_format_process_status():
    """処理状況フォーマットテスト"""
    result = {"status": "completed", "url": "https://example.com", "title": "Test Page"}

    formatted = format_process_status(result, 123)

    assert "📊 処理状況" in formatted
    assert "ID: 123" in formatted
    assert "https://example.com" in formatted
    assert "Test Page" in formatted
    assert "✅ completed" in formatted


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
