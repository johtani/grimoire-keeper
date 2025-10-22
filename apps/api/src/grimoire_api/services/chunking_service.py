"""Text chunking service using Chonkie."""

from pathlib import Path

from chonkie import MarkdownChef, RecursiveChunker
from chonkie.types import MarkdownDocument


class ChunkingService:
    """テキストチャンキングサービス."""

    def __init__(self, chunk_size: int = 1000):
        """初期化.

        Args:
            chunk_size: チャンクサイズ
        """
        self.chef = MarkdownChef()

        # markdown_jp.jsonのパスを取得
        config_dir = Path(__file__).parent.parent / "config"
        recipe_path = config_dir / "markdown_jp.json"

        self.chunker = RecursiveChunker.from_recipe(
            path=str(recipe_path), chunk_size=chunk_size
        )

    def chunk_text(self, text: str) -> list[str]:
        """テキストをチャンクに分割.

        Args:
            text: 分割するテキスト

        Returns:
            チャンクのリスト
        """
        doc = self.chef.parse(text)
        chunked_doc = self.chunker.chunk_document(doc)
        return [chunk.text for chunk in chunked_doc.chunks]




