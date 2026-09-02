"""Slack Block Kit ユーティリティ"""

from typing import Any

from ..models.api import ProcessStatusResponse


def create_url_processing_blocks(page_id: int, url: str) -> list[dict[str, Any]]:
    """URL処理開始時のブロック"""
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"✅ *URL処理を開始しました*\n\n🔗 {url}\n📋 処理ID: `{page_id}`"
                ),
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "📊 ステータス確認"},
                    "action_id": "check_status",
                    "value": str(page_id),
                    "style": "primary",
                }
            ],
        },
    ]


def create_search_result_blocks(
    results: list[dict[str, Any]], query: str
) -> list[dict[str, Any]]:
    """検索結果のブロック"""
    if not results:
        return [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"🔍 '{query}' に一致する結果が見つかりませんでした。",
                },
            }
        ]

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"🔍 検索結果 ({len(results)}件)"},
        }
    ]

    for i, item in enumerate(results[:3], 1):  # 最大3件表示
        title = item.get("title", "No Title")
        url = item.get("url", "")
        summary = item.get("summary", "")
        content = item.get("content", "")
        keywords = item.get("keywords", [])

        if len(summary) > 150:
            summary = summary[:150] + "..."

        # コンテンツを100文字に制限
        if len(content) > 100:
            content = content[:100] + "..."

        text = f"*{i}. {title}*\n🔗 <{url}|リンクを開く>\n"
        if summary:
            text += f"📝 {summary}\n"
        if content:
            text += f"📄 {content}\n"
        if keywords:
            text += f"🏷️ {', '.join(keywords[:3])}"

        block = {"type": "section", "text": {"type": "mrkdwn", "text": text}}

        # 類似検索ボタンを追加
        if keywords:
            block["accessory"] = {
                "type": "button",
                "text": {"type": "plain_text", "text": "類似検索"},
                "action_id": "search_similar",
                "value": " ".join(keywords[:2]),
            }

        blocks.append(block)

        # 区切り線
        if i < len(results) and i < 3:
            blocks.append({"type": "divider"})

    return blocks


def create_status_blocks(
    result: ProcessStatusResponse, page_id: int
) -> list[dict[str, Any]]:
    """ステータス表示のブロック"""
    status = result.status.value
    url = result.page.url if result.page else ""
    title = result.page.title if result.page else ""

    status_info = {
        "processing": {"emoji": "⏳", "color": "#ffcc00", "text": "処理中"},
        "completed": {"emoji": "✅", "color": "#36a64f", "text": "完了"},
        "failed": {"emoji": "❌", "color": "#ff0000", "text": "失敗"},
        "error": {"emoji": "❌", "color": "#ff0000", "text": "エラー"},
        "queued": {"emoji": "⏸️", "color": "#cccccc", "text": "待機中"},
    }

    info = status_info.get(status, {"emoji": "❓", "color": "#cccccc", "text": status})

    text = "*処理状況*\n"
    text += f"📋 ID: `{page_id}`\n"
    text += f"🔗 {url}\n"
    if title:
        text += f"📄 {title}\n"
    text += f"{info['emoji']} ステータス: *{info['text']}*"

    return [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]
