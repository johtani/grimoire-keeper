"""スラッシュコマンドハンドラー"""

from slack_bolt.async_app import AsyncApp
from ..services.api_client import ApiClient
from ..utils.formatters import format_search_results, format_process_status, format_error_message
from ..utils.blocks import create_url_processing_blocks, create_search_result_blocks, create_status_blocks
from ..utils.parsers import parse_url_and_memo

def register_command_handlers(app: AsyncApp) -> None:
    """コマンドハンドラーを登録"""
    
    @app.command("/grimoire")
    async def handle_grimoire_command(ack, respond, command):
        """グリモワールコマンド処理"""
        await ack()
        
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
            await respond(help_text)
            return
            
        if text.startswith("status "):
            page_id_str = text[7:].strip()
            if page_id_str.isdigit():
                try:
                    api_client = ApiClient()
                    result = await api_client.get_process_status(int(page_id_str))
                    
                    # Block Kit形式で応答
                    blocks = create_status_blocks(result, int(page_id_str))
                    await respond(blocks=blocks)
                except Exception as e:
                    await respond(f"ステータス確認エラー: {str(e)}")
            else:
                await respond("有効な処理IDを入力してください")
        elif text.startswith("search "):
            query = text[7:].strip()
            if query:
                try:
                    api_client = ApiClient()
                    result = await api_client.search_content(query, limit=5)
                    results = result.get("results", [])
                    
                    # Block Kit形式で応答
                    blocks = create_search_result_blocks(results, query)
                    await respond(blocks=blocks)
                except Exception as e:
                    error_msg = format_error_message(str(e), "検索")
                    await respond(error_msg)
            else:
                await respond("検索語を入力してください")
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
            await respond(help_text)
        else:
            # URLとmemoを分割
            url, memo = parse_url_and_memo(text)
            
            if url:
                try:
                    api_client = ApiClient()
                    result = await api_client.process_url(url, memo)
                    page_id = result.get("page_id")
                    
                    # Block Kit形式で応答
                    blocks = create_url_processing_blocks(page_id, url)
                    await respond(blocks=blocks)
                except Exception as e:
                    await respond(f"エラー: {str(e)}")
            else:
                await respond("有効なURLまたは検索コマンドを入力してください")
