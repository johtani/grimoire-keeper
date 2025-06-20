"""Text chunking utilities."""


class TextChunker:
    """テキストチャンキングクラス."""

    def __init__(self, chunk_size: int = 1000, overlap: int = 200):
        """初期化.

        Args:
            chunk_size: チャンクサイズ（文字数）
            overlap: 重複サイズ（文字数）
        """
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_text(self, text: str) -> list[str]:
        """テキストをチャンクに分割.

        Args:
            text: 分割対象のテキスト

        Returns:
            分割されたチャンクのリスト
        """
        if not text:
            return []

        # 段落単位での分割を優先
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = ""

        for paragraph in paragraphs:
            if len(current_chunk + paragraph) <= self.chunk_size:
                current_chunk += paragraph + "\n\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = paragraph + "\n\n"

        if current_chunk:
            chunks.append(current_chunk.strip())

        # 大きすぎるチャンクを再分割
        final_chunks = []
        for chunk in chunks:
            if len(chunk) <= self.chunk_size:
                final_chunks.append(chunk)
            else:
                sub_chunks = self._split_by_size(chunk)
                final_chunks.extend(sub_chunks)

        return final_chunks

    def _split_by_size(self, text: str) -> list[str]:
        """文字数ベースでの強制分割.

        Args:
            text: 分割対象のテキスト

        Returns:
            分割されたチャンクのリスト
        """
        chunks = []
        start = 0

        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]
            chunks.append(chunk)

            if end >= len(text):
                break

            start = end - self.overlap

        return chunks
