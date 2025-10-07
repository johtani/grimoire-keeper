"""Grimoire Bot メインアプリケーション"""

import asyncio
import os

from dotenv import load_dotenv
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp

from .handlers.actions import register_action_handlers
from .handlers.commands import register_command_handlers
from .handlers.events import register_event_handlers
from .handlers.modals import register_modal_handlers

load_dotenv()

# Slack App初期化
app = AsyncApp(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
)

# ハンドラー登録
register_event_handlers(app)
register_command_handlers(app)
register_action_handlers(app)
register_modal_handlers(app)


async def start_bot() -> None:
    """ボット開始"""
    handler = AsyncSocketModeHandler(app, os.environ.get("SLACK_APP_TOKEN"))
    await handler.start_async()


if __name__ == "__main__":
    asyncio.run(start_bot())
