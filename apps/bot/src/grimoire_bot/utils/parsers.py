"""Text parsing utilities."""

import re


def parse_url_and_memo(text: str) -> tuple[str | None, str | None]:
    """URLとmemoを分割して抽出.

    Args:
        text: 入力テキスト

    Returns:
        (url, memo) のタプル
    """
    text = text.strip()

    # URL正規表現
    url_pattern = r"https?://[^\s]+"
    url_match = re.search(url_pattern, text)

    if not url_match:
        return None, None

    url = url_match.group()

    # URLを除いた部分をmemoとする
    memo_text = text.replace(url, "").strip()
    # 連続する空白を1つにまとめる
    memo_text = " ".join(memo_text.split())
    memo = memo_text if memo_text else None

    return url, memo
