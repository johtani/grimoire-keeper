"""ハンドラーのテスト"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from grimoire_bot.handlers.commands import GRIMOIRE_HELP_TEXT, register_command_handlers
from grimoire_bot.handlers.events import register_event_handlers
from grimoire_bot.models.api import ProcessStatusResponse
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


@pytest.mark.asyncio
async def test_search_command_renders_api_contract_fixture(bot_contract_fixture):
    """検索コマンドが API 契約のレスポンスを Block Kit に変換する."""
    app = Mock(spec=App)
    register_command_handlers(app)
    handler = app.command.return_value.call_args.args[0]
    api_response = bot_contract_fixture("search.json")
    ack = AsyncMock()
    respond = AsyncMock()

    with patch("grimoire_bot.handlers.commands.ApiClient") as api_client:
        api_client.return_value.search_content = AsyncMock(return_value=api_response)
        await handler(
            ack,
            respond,
            {"user_id": "U123", "text": "search contract testing"},
        )

    ack.assert_awaited_once_with()
    blocks = respond.await_args.kwargs["blocks"]
    assert "Contract Test Article" in blocks[1]["text"]["text"]


@pytest.mark.asyncio
async def test_search_command_does_not_record_search_terms_in_spans(
    bot_contract_fixture,
):
    app = Mock(spec=App)
    register_command_handlers(app)
    handler = app.command.return_value.call_args.args[0]
    parent_span = MagicMock()
    search_span = MagicMock()
    contexts = [
        MagicMock(__enter__=Mock(return_value=parent_span), __exit__=Mock()),
        MagicMock(__enter__=Mock(return_value=search_span), __exit__=Mock()),
    ]

    with (
        patch("grimoire_bot.handlers.commands.tracer") as tracer,
        patch("grimoire_bot.handlers.commands.ApiClient") as api_client,
    ):
        tracer.start_as_current_span.side_effect = contexts
        api_client.return_value.search_content = AsyncMock(
            return_value=bot_contract_fixture("search.json")
        )
        await handler(
            AsyncMock(),
            AsyncMock(),
            {"user_id": "U123", "text": "search private terms"},
        )

    recorded = str(parent_span.set_attribute.call_args_list)
    recorded += str(search_span.set_attribute.call_args_list)
    assert "private terms" not in recorded
    search_span.set_attribute.assert_any_call("search.query_length", 13)


@pytest.mark.asyncio
async def test_status_command_renders_nested_page_contract(bot_contract_fixture):
    """ステータスコマンドが page 配下の API 項目を表示する."""
    app = Mock(spec=App)
    register_command_handlers(app)
    handler = app.command.return_value.call_args.args[0]
    api_response = ProcessStatusResponse.model_validate(
        bot_contract_fixture("process_status.json")
    )
    ack = AsyncMock()
    respond = AsyncMock()

    with patch("grimoire_bot.handlers.commands.ApiClient") as api_client:
        api_client.return_value.get_process_status = AsyncMock(
            return_value=api_response
        )
        await handler(
            ack,
            respond,
            {"user_id": "U123", "text": "status 123"},
        )

    ack.assert_awaited_once_with()
    blocks = respond.await_args.kwargs["blocks"]
    assert "https://example.com/article" in blocks[0]["text"]["text"]
    assert "Contract Test Article" in blocks[0]["text"]["text"]


@pytest.mark.asyncio
async def test_app_mention_uses_process_url_contract(bot_contract_fixture):
    """メンションイベントが API 契約の page_id を応答に利用する."""
    app = Mock(spec=App)
    register_event_handlers(app)
    handler = app.event.return_value.call_args_list[0].args[0]
    api_response = bot_contract_fixture("process_url.json")
    say = AsyncMock()

    with patch("grimoire_bot.handlers.events.ApiClient") as api_client:
        api_client.return_value.process_url = AsyncMock(return_value=api_response)
        await handler(
            {"user": "U123", "text": "<@BOT> https://example.com/article"},
            say,
        )

    assert say.await_count == 2
    assert "処理ID: 123" in say.await_args_list[1].args[0]


@pytest.mark.asyncio
async def test_message_event_log_does_not_include_payload() -> None:
    app = Mock(spec=App)
    register_event_handlers(app)
    handler = app.event.return_value.call_args_list[1].args[0]
    logger = MagicMock()

    await handler(
        {"event": {"type": "message", "text": "private memo"}},
        logger,
    )

    assert "private memo" not in str(logger.info.call_args)
    logger.info.assert_called_once_with(
        "Slack message event received",
        extra={
            "event": "slack.message.received",
            "slack_event_type": "message",
            "has_text": True,
        },
    )
