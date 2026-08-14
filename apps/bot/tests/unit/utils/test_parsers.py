"""Test parsers utilities."""

from grimoire_bot.utils.parsers import parse_url_and_memo


class TestParseUrlAndMemo:
    """Test parse_url_and_memo function."""

    def test_url_with_memo(self):
        """Test URL with memo."""
        text = "https://example.com 面白い記事"
        url, memo = parse_url_and_memo(text)

        assert url == "https://example.com"
        assert memo == "面白い記事"

    def test_url_only(self):
        """Test URL only."""
        text = "https://example.com"
        url, memo = parse_url_and_memo(text)

        assert url == "https://example.com"
        assert memo is None

    def test_memo_before_url(self):
        """Test memo before URL."""
        text = "面白い記事 https://example.com"
        url, memo = parse_url_and_memo(text)

        assert url == "https://example.com"
        assert memo == "面白い記事"

    def test_memo_around_url(self):
        """Test memo around URL."""
        text = "これは https://example.com 面白い記事です"
        url, memo = parse_url_and_memo(text)

        assert url == "https://example.com"
        assert memo == "これは 面白い記事です"

    def test_no_url(self):
        """Test text without URL."""
        text = "面白い記事"
        url, memo = parse_url_and_memo(text)

        assert url is None
        assert memo is None

    def test_empty_text(self):
        """Test empty text."""
        text = ""
        url, memo = parse_url_and_memo(text)

        assert url is None
        assert memo is None

    def test_http_url(self):
        """Test HTTP URL."""
        text = "http://example.com テスト"
        url, memo = parse_url_and_memo(text)

        assert url == "http://example.com"
        assert memo == "テスト"

    def test_url_with_path(self):
        """Test URL with path."""
        text = "https://example.com/path/to/article 記事"
        url, memo = parse_url_and_memo(text)

        assert url == "https://example.com/path/to/article"
        assert memo == "記事"

    def test_multiple_urls(self):
        """Test multiple URLs (should return first one)."""
        text = "https://example.com https://another.com"
        url, memo = parse_url_and_memo(text)

        assert url == "https://example.com"
        assert memo == "https://another.com"

    def test_slack_formatted_url(self):
        """Slack の山括弧を URL に含めない."""
        url, memo = parse_url_and_memo("<https://example.com/path> 記事")

        assert url == "https://example.com/path"
        assert memo == "記事"

    def test_slack_formatted_url_with_label(self):
        """Slack のリンクラベルを memo に含めない."""
        url, memo = parse_url_and_memo("メモ <https://example.com/path|記事リンク>")

        assert url == "https://example.com/path"
        assert memo == "メモ"

    def test_rich_text_link_takes_priority(self):
        """rich text の link.url をテキスト内 URL より優先する."""
        blocks = [
            {
                "type": "rich_text",
                "elements": [
                    {
                        "type": "rich_text_section",
                        "elements": [
                            {
                                "type": "link",
                                "url": "https://structured.example/article",
                            }
                        ],
                    }
                ],
            }
        ]

        url, memo = parse_url_and_memo(
            "<https://fallback.example/article> 保存用", blocks
        )

        assert url == "https://structured.example/article"
        assert memo == "<https://fallback.example/article> 保存用"
