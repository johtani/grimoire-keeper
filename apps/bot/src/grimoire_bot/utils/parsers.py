"""Text parsing utilities."""

import re
from typing import Any

SLACK_URL_PATTERN = re.compile(r"<(https?://[^>|]+)(?:\|[^>]*)?>")
PLAIN_URL_PATTERN = re.compile(r"https?://[^\s<>]+")


def _find_link_url(value: Any) -> str | None:
    """Slack rich text 内の最初のリンク URL を再帰的に取得する."""
    if isinstance(value, dict):
        if value.get("type") == "link":
            url = value.get("url")
            if isinstance(url, str) and PLAIN_URL_PATTERN.fullmatch(url):
                return url
        for child in value.values():
            url = _find_link_url(child)
            if url:
                return url
    elif isinstance(value, list):
        for child in value:
            url = _find_link_url(child)
            if url:
                return url
    return None


def parse_url_and_memo(
    text: str, blocks: list[dict[str, Any]] | None = None
) -> tuple[str | None, str | None]:
    """URLとmemoを分割して抽出.

    Args:
        text: 入力テキスト
        blocks: Slack イベントの構造化ブロック

    Returns:
        (url, memo) のタプル
    """
    text = text.strip()

    structured_url = _find_link_url(blocks) if blocks else None
    slack_match = SLACK_URL_PATTERN.search(text)
    plain_match = PLAIN_URL_PATTERN.search(text)
    url = structured_url or (slack_match.group(1) if slack_match else None)
    url = url or (plain_match.group() if plain_match else None)

    if not url:
        return None, None

    # URLを除いた部分をmemoとする
    memo_text = text
    if slack_match and slack_match.group(1) == url:
        memo_text = memo_text.replace(slack_match.group(), "", 1)
    else:
        memo_text = memo_text.replace(url, "", 1)
    # 連続する空白を1つにまとめる
    memo_text = " ".join(memo_text.split())
    memo = memo_text if memo_text else None

    return url, memo
