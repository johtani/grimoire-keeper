"""Block Kitユーティリティのテスト"""

import pytest
from grimoire_bot.models.api import ProcessStatusResponse
from grimoire_bot.utils.blocks import (
    create_search_result_blocks,
    create_status_blocks,
    create_url_processing_blocks,
)


def test_create_url_processing_blocks():
    """URL処理ブロック作成テスト"""
    blocks = create_url_processing_blocks(123, "https://example.com")

    assert len(blocks) == 2
    assert blocks[0]["type"] == "section"
    assert "https://example.com" in blocks[0]["text"]["text"]
    assert "123" in blocks[0]["text"]["text"]
    assert blocks[1]["type"] == "actions"
    assert blocks[1]["elements"][0]["action_id"] == "check_status"


def test_create_search_result_blocks_with_results(bot_contract_fixture):
    """検索結果ブロック作成テスト（結果あり）"""
    contract = bot_contract_fixture("search.json")
    results = contract["results"]

    blocks = create_search_result_blocks(results, contract["query"])

    assert len(blocks) >= 2
    assert blocks[0]["type"] == "header"
    assert "検索結果 (1件)" in blocks[0]["text"]["text"]
    assert blocks[1]["type"] == "section"
    assert "Contract Test Article" in blocks[1]["text"]["text"]


def test_create_search_result_blocks_empty():
    """検索結果ブロック作成テスト（結果なし）"""
    blocks = create_search_result_blocks([], "nonexistent")

    assert len(blocks) == 1
    assert blocks[0]["type"] == "section"
    assert "見つかりませんでした" in blocks[0]["text"]["text"]


@pytest.mark.parametrize(
    ("fixture_name", "expected_url", "expected_title", "expected_emoji"),
    [
        (
            "process_status_queued.json",
            "https://example.com/queued",
            "Processing...",
            "⏸️",
        ),
        (
            "process_status_processing.json",
            "https://example.com/processing",
            "Processing article",
            "⏳",
        ),
        (
            "process_status_completed.json",
            "https://example.com/completed",
            "Completed article",
            "✅",
        ),
        (
            "process_status_failed.json",
            "https://example.com/failed",
            "Failed article",
            "❌",
        ),
    ],
)
def test_create_status_blocks(
    bot_contract_fixture,
    fixture_name,
    expected_url,
    expected_title,
    expected_emoji,
):
    """API 契約の4状態を正しく表示する."""
    result = ProcessStatusResponse.model_validate(bot_contract_fixture(fixture_name))

    blocks = create_status_blocks(result, result.page.id)

    assert len(blocks) == 1
    assert blocks[0]["type"] == "section"
    assert str(result.page.id) in blocks[0]["text"]["text"]
    assert expected_url in blocks[0]["text"]["text"]
    assert expected_title in blocks[0]["text"]["text"]
    assert expected_emoji in blocks[0]["text"]["text"]
