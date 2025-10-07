"""イベントハンドラー"""

from slack_bolt.async_app import AsyncApp
from ..services.api_client import ApiClient
from ..utils.parsers import parse_url_and_memo

def register_event_handlers(app: AsyncApp) -> None:
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
            
        # URLとmemoを分割
        url, memo = parse_url_and_memo(clean_text)
        
        if url:
            await say(f"<@{user}> URLを処理中です...")
            try:
                api_client = ApiClient()
                result = await api_client.process_url(url, memo)
                page_id = result.get("page_id")
                memo_text = f"\nメモ: {memo}" if memo else ""
                await say(f"<@{user}> URL処理を開始しました！\n処理ID: {page_id}{memo_text}\n完了まで少々お待ちください。")
            except Exception as e:
                await say(f"<@{user}> エラーが発生しました: {str(e)}")
        else:
            await say(f"<@{user}> URLが見つかりません。有効なURLを教えてください。")
    
    @app.event("message")
    async def handle_message_events(body, logger):
        """メッセージイベント（ログ用）"""
        logger.info(body)