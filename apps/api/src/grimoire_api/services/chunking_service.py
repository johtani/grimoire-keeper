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
        doc = self._parse_markdown_string(text)
        chunked_doc = self.chunker.chunk_document(doc)
        return [chunk.text for chunk in chunked_doc.chunks]

    def _parse_markdown_string(self, markdown_text: str) -> MarkdownDocument:
        """Markdown文字列を解析してMarkdownDocumentを返す.

        Args:
            markdown_text: 解析するMarkdown文字列

        Returns:
            MarkdownDocument
        """
        # MarkdownChefのprocessメソッドの処理を模倣
        tables = self.chef.prepare_tables(markdown_text)
        code = self.chef.prepare_code(markdown_text)
        images = self.chef.extract_images(markdown_text)

        return MarkdownDocument(
            content=markdown_text,
            chunks=[],  # RecursiveChunkerで後から分割
            tables=tables,
            code=code,
            images=images,
        )

    def chunk_markdown(self, markdown_text: str) -> list[str]:
        """Markdownテキストをチャンクに分割.

        Args:
            markdown_text: 分割するMarkdownテキスト

        Returns:
            チャンクのリスト
        """
        return self.chunk_text(markdown_text)
