"""メッセージフォーマッター"""

from typing import List, Dict, Any

def format_search_results(results: List[Dict[str, Any]], query: str) -> str:
    """検索結果をフォーマット"""
    if not results:
        return f"🔍 '{query}' に一致する結果が見つかりませんでした。"
    
    response = f"🔍 検索結果 ({len(results)}件):\n\n"
    for i, item in enumerate(results, 1):
        title = item.get("title", "No Title")
        url = item.get("url", "")
        summary = item.get("summary", "")
        keywords = item.get("keywords", [])
        
        # 要約を100文字に制限
        if len(summary) > 100:
            summary = summary[:100] + "..."
        
        response += f"{i}. **{title}**\n"
        response += f"🔗 {url}\n"
        if summary:
            response += f"📝 {summary}\n"
        if keywords:
            response += f"🏷️ {', '.join(keywords[:3])}\n"
        response += "\n"
    
    return response

def format_process_status(result: Dict[str, Any], page_id: int) -> str:
    """処理状況をフォーマット"""
    status = result.get("status", "unknown")
    url = result.get("url", "")
    title = result.get("title", "")
    
    status_emoji = {
        "processing": "⏳",
        "completed": "✅", 
        "failed": "❌",
        "pending": "⏸️"
    }.get(status, "❓")
    
    response = f"📊 処理状況\n"
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