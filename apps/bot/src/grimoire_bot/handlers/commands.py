"""スラッシュコマンドハンドラー"""

from grimoire_shared.telemetry import get_meter, get_tracer
from slack_bolt.async_app import AsyncApp

from ..services.api_client import ApiClient
from ..utils.blocks import (
    create_search_result_blocks,
    create_status_blocks,
    create_url_processing_blocks,
)
from ..utils.parsers import parse_url_and_memo

tracer = get_tracer(__name__)
meter = get_meter(__name__)

# メトリクスの定義
command_counter = meter.create_counter(
    "slack_commands_total", description="Total number of Slack commands processed"
)
command_duration = meter.create_histogram(
    "slack_command_duration_seconds", description="Duration of Slack command processing"
)
url_processing_counter = meter.create_counter(
    "url_processing_requests_total",
    description="Total number of URL processing requests",
)
search_counter = meter.create_counter(
    "search_requests_total", description="Total number of search requests"
)


def register_command_handlers(app: AsyncApp) -> None:
    """コマンドハンドラーを登録"""

    @app.command("/grimoire")
    async def handle_grimoire_command(ack, respond, command):
        """グリモワールコマンド処理"""
        import time

        start_time = time.time()

        with tracer.start_as_current_span("slack_command_grimoire") as span:
            span.set_attribute("slack.command", "/grimoire")
            span.set_attribute("slack.user_id", command["user_id"])

            await ack()

            text = command["text"].strip()
            span.set_attribute("command.text", text)

            # コマンドタイプを判定
            if not text:
                command_type = "help"
            elif text.startswith("status "):
                command_type = "status"
            elif text.startswith("search "):
                command_type = "search"
            elif text == "help":
                command_type = "help"
            else:
                command_type = "process_url"

            span.set_attribute("command.type", command_type)

            try:
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

                elif text.startswith("status "):
                    with tracer.start_as_current_span("command_status"):
                        page_id_str = text[7:].strip()
                        if page_id_str.isdigit():
                            api_client = ApiClient()
                            result = await api_client.get_process_status(
                                int(page_id_str)
                            )
                            blocks = create_status_blocks(result, int(page_id_str))
                            await respond(blocks=blocks)
                        else:
                            await respond("有効な処理IDを入力してください")

                elif text.startswith("search "):
                    with tracer.start_as_current_span("command_search") as search_span:
                        query = text[7:].strip()
                        search_span.set_attribute("search.query", query)
                        if query:
                            api_client = ApiClient()
                            result = await api_client.search_content(query, limit=5)
                            results = result.get("results", [])
                            search_span.set_attribute(
                                "search.results_count", len(results)
                            )
                            search_counter.add(1, {"query_length": str(len(query))})
                            blocks = create_search_result_blocks(results, query)
                            await respond(blocks=blocks)
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
                    with tracer.start_as_current_span(
                        "command_process_url"
                    ) as url_span:
                        url, memo = parse_url_and_memo(text)
                        url_span.set_attribute("url.value", url or "")
                        url_span.set_attribute("url.memo", memo or "")

                        if url:
                            api_client = ApiClient()
                            result = await api_client.process_url(url, memo)
                            page_id = result.get("page_id")
                            url_span.set_attribute("process.page_id", page_id or 0)
                            url_processing_counter.add(1, {"has_memo": str(bool(memo))})
                            blocks = create_url_processing_blocks(page_id, url)
                            await respond(blocks=blocks)
                        else:
                            await respond(
                                "有効なURLまたは検索コマンドを入力してください"
                            )

                # 成功メトリクス
                command_counter.add(
                    1, {"command_type": command_type, "status": "success"}
                )

            except Exception as e:
                # エラーメトリクス
                command_counter.add(
                    1, {"command_type": command_type, "status": "error"}
                )
                span.set_attribute("error", True)
                span.set_attribute("error.message", str(e))
                await respond(f"エラー: {str(e)}")

            finally:
                # 持続時間メトリクス
                duration = time.time() - start_time
                command_duration.record(duration, {"command_type": command_type})
