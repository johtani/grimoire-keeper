"""モーダルハンドラー"""

from slack_bolt.async_app import AsyncApp

from ..services.api_client import ApiClient
from ..utils.blocks import create_url_processing_blocks


def register_modal_handlers(app: AsyncApp) -> None:
    """モーダルハンドラーを登録"""

    @app.shortcut("add_url")
    async def handle_add_url_shortcut(ack, shortcut, client):
        """URL追加ショートカット"""
        await ack()

        modal_view = {
            "type": "modal",
            "callback_id": "url_submission",
            "title": {"type": "plain_text", "text": "URL追加"},
            "submit": {"type": "plain_text", "text": "処理開始"},
            "close": {"type": "plain_text", "text": "キャンセル"},
            "blocks": [
                {
                    "type": "input",
                    "block_id": "url_input",
                    "element": {
                        "type": "url_text_input",
                        "action_id": "url_value",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "https://example.com",
                        },
                    },
                    "label": {"type": "plain_text", "text": "URL"},
                },
                {
                    "type": "input",
                    "block_id": "memo_input",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "memo_value",
                        "placeholder": {"type": "plain_text", "text": "メモ（任意）"},
                        "multiline": True,
                    },
                    "label": {"type": "plain_text", "text": "メモ"},
                    "optional": True,
                },
            ],
        }

        await client.views_open(trigger_id=shortcut["trigger_id"], view=modal_view)

    @app.view("url_submission")
    async def handle_url_submission(ack, body, client):
        """URL送信処理"""
        values = body["view"]["state"]["values"]
        url = values["url_input"]["url_value"]["value"]
        memo = values["memo_input"]["memo_value"].get("value", "")

        # バリデーション
        if not url or not url.startswith(("http://", "https://")):
            await ack(
                response_action="errors",
                errors={"url_input": "有効なURLを入力してください"},
            )
            return

        await ack()

        try:
            api_client = ApiClient()
            result = await api_client.process_url(url, memo if memo else None)
            page_id = result.get("page_id")

            # 結果をチャンネルに投稿
            blocks = create_url_processing_blocks(page_id, url)
            await client.chat_postMessage(
                channel=body["user"]["id"],  # DMで送信
                blocks=blocks,
            )

        except Exception as e:
            await client.chat_postMessage(
                channel=body["user"]["id"], text=f"❌ エラーが発生しました: {str(e)}"
            )
