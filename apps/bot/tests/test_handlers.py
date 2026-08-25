"""ハンドラーのテスト"""

from unittest.mock import AsyncMock, Mock

import pytest
from grimoire_bot.handlers.commands import GRIMOIRE_HELP_TEXT, register_command_handlers
from grimoire_bot.handlers.events import register_event_handlers
from slack_bolt import App


@pytest.fixture
def mock_app():
    """モックSlack Appのフィクスチャ"""
    return Mock(spec=App)


def test_register_event_handlers(mock_app):
    """イベントハンドラー登録テスト"""
    register_event_handlers(mock_app)

    # app.eventが呼ばれたことを確認
    assert mock_app.event.call_count >= 2


def test_register_command_handlers(mock_app):
    """コマンドハンドラー登録テスト"""
    register_command_handlers(mock_app)

    # app.commandが呼ばれたことを確認
    assert mock_app.command.call_count >= 1


def test_app_mention_handler():
    """メンションハンドラーのテスト"""
    app = Mock(spec=App)
    register_event_handlers(app)

    # イベントハンドラーが登録されたことを確認
    assert app.event.call_count == 2  # app_mentionとmessageイベント


def test_grimoire_command_handler():
    """グリモワールコマンドハンドラーのテスト"""
    app = Mock(spec=App)
    register_command_handlers(app)

    # コマンドハンドラーが登録されたことを確認
    assert app.command.call_count == 1  # /grimoireコマンド


@pytest.mark.asyncio
async def test_grimoire_help_response_is_same_for_empty_text_and_help():
    """引数なしとhelpで同じヘルプが返ることを確認"""
    app = Mock(spec=App)
    register_command_handlers(app)
    handler = app.command.return_value.call_args.args[0]
    responses = []

    for text in ("", "help"):
        ack = AsyncMock()
        respond = AsyncMock()

        await handler(ack, respond, {"user_id": "U123", "text": text})

        ack.assert_awaited_once_with()
        respond.assert_awaited_once_with(GRIMOIRE_HELP_TEXT)
        responses.append(respond.await_args.args[0])

    assert responses[0] == responses[1]
