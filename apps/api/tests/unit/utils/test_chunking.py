"""Test text chunking utilities."""

from typing import Any

from grimoire_api.utils.chunking import TextChunker


class TestTextChunker:
    """TextChunkerのテストクラス."""

    def test_init_default_values(self: Any) -> None:
        """デフォルト値での初期化テスト."""
        chunker = TextChunker()
        assert chunker.chunk_size == 1000
        assert chunker.overlap == 200

    def test_init_custom_values(self: Any) -> None:
        """カスタム値での初期化テスト."""
        chunker = TextChunker(chunk_size=500, overlap=100)
        assert chunker.chunk_size == 500
        assert chunker.overlap == 100

    def test_chunk_empty_text(self: Any) -> None:
        """空文字列のチャンキングテスト."""
        chunker = TextChunker()
        result = chunker.chunk_text("")
        assert result == []

    def test_chunk_short_text(self: Any) -> None:
        """短いテキストのチャンキングテスト."""
        chunker = TextChunker(chunk_size=100, overlap=20)
        text = "This is a short text."
        result = chunker.chunk_text(text)
        assert len(result) == 1
        assert result[0] == text

    def test_chunk_paragraph_based(self: Any) -> None:
        """段落ベースのチャンキングテスト."""
        chunker = TextChunker(chunk_size=50, overlap=10)
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        result = chunker.chunk_text(text)

        # 各段落が適切に分割されることを確認
        assert len(result) >= 2
        assert "First paragraph." in result[0]

    def test_chunk_with_overlap(self: Any) -> None:
        """重複ありのチャンキングテスト."""
        chunker = TextChunker(chunk_size=20, overlap=5)
        text = "a" * 50  # 50文字の文字列
        result = chunker.chunk_text(text)

        # 複数のチャンクに分割されることを確認
        assert len(result) > 1
        # 各チャンクのサイズが適切であることを確認
        for chunk in result[:-1]:  # 最後のチャンク以外
            assert len(chunk) <= chunker.chunk_size

    def test_split_by_size(self: Any) -> None:
        """文字数ベース分割のテスト."""
        chunker = TextChunker(chunk_size=10, overlap=3)
        text = "a" * 25
        result = chunker._split_by_size(text)

        # 適切に分割されることを確認
        assert len(result) == 4  # 25文字、chunk_size=10、overlap=3の場合は4チャンク
        assert len(result[0]) == 10
        assert len(result[1]) == 10
        assert len(result[2]) == 10
        assert len(result[3]) == 4  # 最後のチャンク

    def test_chunk_mixed_content(self: Any) -> None:
        """混合コンテンツのチャンキングテスト."""
        chunker = TextChunker(chunk_size=100, overlap=20)
        text = """# Title

This is the first paragraph with some content.

## Subtitle

This is the second paragraph with more content.

- List item 1
- List item 2
- List item 3

Final paragraph."""

        result = chunker.chunk_text(text)
        assert len(result) >= 1
        # 最初のチャンクにタイトルが含まれることを確認
        assert "# Title" in result[0]
