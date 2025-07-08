"""アクションハンドラーのテスト"""

import pytest
from unittest.mock import Mock
from grimoire_bot.handlers.actions import register_action_handlers

@pytest.fixture
def mock_app():
    """モックSlack Appのフィクスチャ"""
    return Mock()

def test_register_action_handlers(mock_app):
    """アクションハンドラー登録テスト"""
    register_action_handlers(mock_app)
    
    # app.actionが呼ばれたことを確認
    assert mock_app.action.call_count >= 2
    
    # 登録されたアクションIDを確認
    action_calls = [call[0][0] for call in mock_app.action.call_args_list]
    assert "check_status" in action_calls
    assert "search_similar" in action_calls