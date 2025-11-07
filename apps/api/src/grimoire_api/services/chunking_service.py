"""Text chunking service using Chonkie."""

from pathlib import Path
from typing import Any

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
        self.chunk_size = chunk_size
        self.config_dir = Path(__file__).parent.parent / "config"
        
        # デフォルトチャンカー（日本語）
        self.default_chunker = self._create_chunker("markdown_jp.json")

    def _create_chunker(self, recipe_file: str) -> RecursiveChunker:
        """レシピファイルからチャンカーを作成.
        
        Args:
            recipe_file: レシピファイル名
            
        Returns:
            RecursiveChunkerインスタンス
        """
        recipe_path = self.config_dir / recipe_file
        if recipe_path.exists():
            return RecursiveChunker.from_recipe(
                path=str(recipe_path), chunk_size=self.chunk_size
            )
        # ファイルがない場合はデフォルトチャンカーを作成
        return RecursiveChunker(chunk_size=self.chunk_size)

    def _get_chunker_for_language(self, language: str | None) -> RecursiveChunker:
        """言語に応じたチャンカーを取得.
        
        Args:
            language: 言語コードまたは言語名
            
        Returns:
            適切なチャンカー
        """
        if not language:
            return self.default_chunker
            
        # 言語コードを正規化
        lang_code = language.lower().strip()
        
        # 英語の場合は英語レシピを使用
        if lang_code in ['en', 'english']:
            return RecursiveChunker.from_recipe(
                "markdown", lang="en", chunk_size=self.chunk_size
            )
            
        # それ以外は日本語レシピを使用（デフォルト）
        return self.default_chunker

    def chunk_text(self, text: str, language: str | None = None) -> list[str]:
        """テキストをチャンクに分割.

        Args:
            text: 分割するテキスト
            language: 言語情報（オプション）

        Returns:
            チャンクのリスト
        """
        chunker = self._get_chunker_for_language(language)
        doc = self.chef.parse(text)
        chunked_doc = chunker.chunk_document(doc)
        return [chunk.text for chunk in chunked_doc.chunks]
        
    def chunk_text_with_jina_data(self, text: str, jina_data: dict[str, Any]) -> list[str]:
        """ジナデータから言語情報を抽出してチャンキング.
        
        Args:
            text: 分割するテキスト
            jina_data: Jina AI Readerのレスポンスデータ
            
        Returns:
            チャンクのリスト
        """
        # Jina AI Readerのレスポンスから言語情報を抽出
        language = None
        if 'data' in jina_data:
            data = jina_data['data']
            # 一般的な言語フィールドをチェック
            language = (
                data.get('language') or 
                data.get('lang') or 
                data.get('detected_language') or
                data.get('content_language')
            )
            
        return self.chunk_text(text, language)




