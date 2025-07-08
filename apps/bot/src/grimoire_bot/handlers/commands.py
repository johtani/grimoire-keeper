"""スラッシュコマンドハンドラー"""

from slack_bolt import App
from ..services.api_client import ApiClient

def register_command_handlers(app: App) -> None:
    """コマンドハンドラーを登録"""
    
    @app.command("/grimoire")
    def handle_grimoire_command(ack, respond, command):
        """グリモワールコマンド処理"""
        ack()
        
        text = command["text"].strip()
        user_id = command["user_id"]
        
        if not text:
            respond("使用方法: `/grimoire <URL>` または `/grimoire search <検索語>`")
            return
            
        if text.startswith("search "):
            query = text[7:].strip()
            if query:
                respond(f"検索中: {query}")
                # TODO: 検索API連携
            else:
                respond("検索語を入力してください")
        elif "http" in text:
            respond(f"URL処理中: {text}")
            # TODO: URL処理API連携
        else:
            respond("有効なURLまたは検索コマンドを入力してください")