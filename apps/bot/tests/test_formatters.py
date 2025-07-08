"""フォーマッターのテスト"""

import pytest
from grimoire_bot.utils.formatters import (
    format_search_results,
    format_process_status,
    format_error_message
)

def test_format_search_results_with_results():
    """検索結果ありのフォーマットテスト"""
    results = [
        {
            "title": "Test Article",
            "url": "https://example.com",
            "summary": "This is a test article about AI and machine learning.",
            "keywords": ["AI", "ML", "test"]
        }
    ]
    
    formatted = format_search_results(results, "AI")
    
    assert "🔍 検索結果 (1件)" in formatted
    assert "Test Article" in formatted
    assert "https://example.com" in formatted
    assert "AI, ML, test" in formatted

def test_format_search_results_empty():
    """検索結果なしのフォーマットテスト"""
    results = []
    formatted = format_search_results(results, "nonexistent")
    
    assert "一致する結果が見つかりませんでした" in formatted
    assert "nonexistent" in formatted

def test_format_process_status():
    """処理状況フォーマットテスト"""
    result = {
        "status": "completed",
        "url": "https://example.com",
        "title": "Test Page"
    }
    
    formatted = format_process_status(result, 123)
    
    assert "📊 処理状況" in formatted
    assert "ID: 123" in formatted
    assert "https://example.com" in formatted
    assert "Test Page" in formatted
    assert "✅ completed" in formatted

def test_format_error_message():
    """エラーメッセージフォーマットテスト"""
    formatted = format_error_message("Connection failed", "URL処理")
    
    assert "❌ エラーが発生しました" in formatted
    assert "操作: URL処理" in formatted
    assert "詳細: Connection failed" in formatted
    assert "管理者にお問い合わせ" in formatted