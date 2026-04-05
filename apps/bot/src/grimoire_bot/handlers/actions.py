"""ボタンアクションハンドラー"""

from typing import Any

from slack_bolt.async_app import AsyncAck, AsyncApp
from slack_bolt.context.respond.async_respond import AsyncRespond

from ..services.api_client import ApiClient
from ..utils.formatters import format_error_message, format_process_status


def register_action_handlers(app: AsyncApp) -> None:
    """アクションハンドラーを登録"""

    @app.action("check_status")
    async def handle_check_status(
        ack: AsyncAck, body: dict[str, Any], respond: AsyncRespond
    ) -> None:
        """ステータス確認ボタン"""
        await ack()

        page_id = body["actions"][0]["value"]
        try:
            api_client = ApiClient()
            result = await api_client.get_process_status(int(page_id))
            response = format_process_status(result, int(page_id))
            await respond(response)
        except Exception as e:
            error_msg = format_error_message(str(e), "ステータス確認")
            await respond(error_msg)

    @app.action("search_similar")
    async def handle_search_similar(
        ack: AsyncAck, body: dict[str, Any], respond: AsyncRespond
    ) -> None:
        """類似検索ボタン"""
        await ack()

        keywords = body["actions"][0]["value"]
        try:
            api_client = ApiClient()
            result = await api_client.search_content(keywords, limit=3)
            results = result.get("results", [])

            if results:
                response = f"🔍 '{keywords}' の類似コンテンツ:\n\n"
                for i, item in enumerate(results, 1):
                    title = item.get("title", "No Title")
                    url = item.get("url", "")
                    response += f"{i}. **{title}**\n🔗 {url}\n\n"
            else:
                response = f"'{keywords}' に類似するコンテンツが見つかりませんでした。"

            await respond(response)
        except Exception as e:
            error_msg = format_error_message(str(e), "類似検索")
            await respond(error_msg)
