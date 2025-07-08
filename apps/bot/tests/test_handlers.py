"""ハンドラーのテスト"""

import pytest
from unittest.mock import Mock, patch
from slack_bolt import App
from grimoire_bot.handlers.events import register_event_handlers
from grimoire_bot.handlers.commands import register_command_handlers

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