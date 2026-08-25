"""メッセージフォーマッター"""

from typing import Any


def format_process_status(result: dict[str, Any], page_id: int) -> str:
    """処理状況をフォーマット"""
    status = result.get("status", "unknown")
    url = result.get("url", "")
    title = result.get("title", "")

    status_emoji = {
        "processing": "⏳",
        "completed": "✅",
        "failed": "❌",
        "pending": "⏸️",
    }.get(status, "❓")

    response = "📊 処理状況\n"
    response += f"ID: {page_id}\n"
    response += f"URL: {url}\n"
    if title:
        response += f"タイトル: {title}\n"
    response += f"ステータス: {status_emoji} {status}\n"

    return response


def format_error_message(error: str, context: str = "") -> str:
    """エラーメッセージをフォーマット"""
    response = "❌ エラーが発生しました\n"
    if context:
        response += f"操作: {context}\n"
    response += f"詳細: {error}\n"
    response += "\n💡 問題が続く場合は管理者にお問い合わせください。"
    return response
