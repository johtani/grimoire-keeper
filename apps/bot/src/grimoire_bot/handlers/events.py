"""イベントハンドラー"""

from slack_bolt import App
from ..services.api_client import ApiClient

def register_event_handlers(app: App) -> None:
    """イベントハンドラーを登録"""
    
    @app.event("app_mention")
    async def handle_app_mention(event, say):
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
            try:
                api_client = ApiClient()
                result = await api_client.process_url(clean_text)
                page_id = result.get("page_id")
                say(f"<@{user}> URL処理を開始しました！\n処理ID: {page_id}\n完了まで少々お待ちください。")
            except Exception as e:
                say(f"<@{user}> エラーが発生しました: {str(e)}")
        else:
            say(f"<@{user}> URLが見つかりません。有効なURLを教えてください。")
    
    @app.event("message")
    def handle_message_events(body, logger):
        """メッセージイベント（ログ用）"""
        logger.info(body)