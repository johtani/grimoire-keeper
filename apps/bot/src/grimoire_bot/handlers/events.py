"""イベントハンドラー"""

from slack_bolt import App
from ..services.api_client import ApiClient

def register_event_handlers(app: App) -> None:
    """イベントハンドラーを登録"""
    
    @app.event("app_mention")
    def handle_app_mention(event, say):
        """メンション時の処理"""
        user = event["user"]
        text = event["text"]
        
        # ボットメンションを除去
        clean_text = text.split(">", 1)[-1].strip()
        
        if not clean_text:
            say(f"<@{user}> こんにちは！URLを教えてください。")
            return
            
        # URL検出の簡易実装
        if "http" in clean_text:
            say(f"<@{user}> URLを処理中です...")
            # TODO: API連携実装
        else:
            say(f"<@{user}> URLが見つかりません。有効なURLを教えてください。")
    
    @app.event("message")
    def handle_message_events(body, logger):
        """メッセージイベント（ログ用）"""
        logger.info(body)