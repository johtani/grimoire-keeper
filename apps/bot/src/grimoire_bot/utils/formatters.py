"""メッセージフォーマッター"""

from ..models.api import ProcessStatusResponse
from ..services.api_client import ApiClientError

ERROR_MESSAGES = {
    "bad_request": "リクエストを処理できませんでした。",
    "unauthorized": "認証が必要です。",
    "forbidden": "この操作は許可されていません。",
    "not_found": "対象が見つかりませんでした。",
    "method_not_allowed": "この操作は利用できません。",
    "conflict": "現在の状態では操作を実行できません。",
    "validation_error": "入力内容を確認してください。",
    "service_unavailable": "サービスを一時的に利用できません。",
    "internal_error": "サーバーでエラーが発生しました。",
    "connection_error": "APIに接続できませんでした。",
    "invalid_response": "APIから予期しない応答を受信しました。",
}


def format_process_status(result: ProcessStatusResponse, page_id: int) -> str:
    """処理状況をフォーマット"""
    status = result.status.value
    url = result.page.url if result.page else ""
    title = result.page.title if result.page else ""

    status_emoji = {
        "processing": "⏳",
        "completed": "✅",
        "failed": "❌",
        "error": "❌",
        "queued": "⏸️",
    }.get(status, "❓")

    response = "📊 処理状況\n"
    response += f"ID: {page_id}\n"
    response += f"URL: {url}\n"
    if title:
        response += f"タイトル: {title}\n"
    response += f"ステータス: {status_emoji} {status}\n"

    return response


def format_error_message(error: Exception, context: str = "") -> str:
    """エラーメッセージをフォーマット"""
    response = "❌ エラーが発生しました\n"
    if context:
        response += f"操作: {context}\n"
    code = error.code if isinstance(error, ApiClientError) else "api_error"
    response += f"詳細: {ERROR_MESSAGES.get(code, '操作に失敗しました。')}\n"
    if isinstance(error, ApiClientError) and error.request_id:
        response += f"リクエストID: {error.request_id}\n"
    response += "\n💡 問題が続く場合は管理者にお問い合わせください。"
    return response
