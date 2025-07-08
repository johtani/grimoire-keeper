"""Grimoire Bot メインアプリケーション"""

import os
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv

from .handlers.events import register_event_handlers
from .handlers.commands import register_command_handlers
from .handlers.actions import register_action_handlers
from .handlers.modals import register_modal_handlers

load_dotenv()

# Slack App初期化
app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET")
)

# ハンドラー登録
register_event_handlers(app)
register_command_handlers(app)
register_action_handlers(app)
register_modal_handlers(app)

def start_bot() -> None:
    """ボット開始"""
    handler = SocketModeHandler(app, os.environ.get("SLACK_APP_TOKEN"))
    handler.start()

if __name__ == "__main__":
    start_bot()