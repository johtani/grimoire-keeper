"""スラッシュコマンドハンドラー"""

from slack_bolt import App
from ..services.api_client import ApiClient
from ..utils.formatters import format_search_results, format_process_status, format_error_message

def register_command_handlers(app: App) -> None:
    """コマンドハンドラーを登録"""
    
    @app.command("/grimoire")
    async def handle_grimoire_command(ack, respond, command):
        """グリモワールコマンド処理"""
        ack()
        
        text = command["text"].strip()
        user_id = command["user_id"]
        
        if not text:
            help_text = """📚 **Grimoire Keeper 使用方法**

• `/grimoire <URL>` - URLを処理して要約を作成
• `/grimoire search <検索語>` - コンテンツを検索
• `/grimoire status <処理ID>` - 処理状況を確認
• `/grimoire help` - このヘルプを表示

例:
`/grimoire https://example.com`
`/grimoire search AI`
`/grimoire status 123`"""
            respond(help_text)
            return
            
        if text.startswith("status "):
            page_id_str = text[7:].strip()
            if page_id_str.isdigit():
                try:
                    api_client = ApiClient()
                    result = await api_client.get_process_status(int(page_id_str))
                    response = format_process_status(result, int(page_id_str))
                    respond(response)
                except Exception as e:
                    respond(f"ステータス確認エラー: {str(e)}")
            else:
                respond("有効な処理IDを入力してください")
        elif text.startswith("search "):
            query = text[7:].strip()
            if query:
                try:
                    api_client = ApiClient()
                    result = await api_client.search_content(query, limit=5)
                    results = result.get("results", [])
                    response = format_search_results(results, query)
                    respond(response)
                except Exception as e:
                    error_msg = format_error_message(str(e), "検索")
                    respond(error_msg)
            else:
                respond("検索語を入力してください")
        elif text == "help":
            help_text = """📚 **Grimoire Keeper 使用方法**

• `/grimoire <URL>` - URLを処理して要約を作成
• `/grimoire search <検索語>` - コンテンツを検索
• `/grimoire status <処理ID>` - 処理状況を確認
• `/grimoire help` - このヘルプを表示

例:
`/grimoire https://example.com`
`/grimoire search AI`
`/grimoire status 123`"""
            respond(help_text)
        elif "http" in text:
            try:
                api_client = ApiClient()
                result = await api_client.process_url(text)
                page_id = result.get("page_id")
                respond(f"✅ URL処理を開始しました！\n処理ID: {page_id}\n完了まで少々お待ちください。")
            except Exception as e:
                respond(f"エラー: {str(e)}")
        else:
            respond("有効なURLまたは検索コマンドを入力してください")