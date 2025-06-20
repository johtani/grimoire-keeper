"""Vectorization service for Weaviate."""

import json

import weaviate

from ..config import settings
from ..repositories.file_repository import FileRepository
from ..repositories.page_repository import PageRepository
from ..utils.chunking import TextChunker
from ..utils.exceptions import VectorizerError


class VectorizerService:
    """ベクトル化サービス."""

    def __init__(
        self,
        page_repo: PageRepository,
        file_repo: FileRepository,
        text_chunker: TextChunker,
        weaviate_url: str = None,
    ):
        """初期化.

        Args:
            page_repo: ページリポジトリ
            file_repo: ファイルリポジトリ
            text_chunker: テキストチャンカー
            weaviate_url: Weaviate URL
        """
        self.page_repo = page_repo
        self.file_repo = file_repo
        self.text_chunker = text_chunker
        self.weaviate_url = weaviate_url or settings.WEAVIATE_URL
        self._client = None

    @property
    def client(self):
        """Weaviateクライアント."""
        if self._client is None:
            self._client = weaviate.Client(self.weaviate_url)
        return self._client

    async def vectorize_content(self, page_id: int) -> None:
        """コンテンツのベクトル化とWeaviate保存.

        Args:
            page_id: ページID

        Raises:
            VectorizerError: ベクトル化エラー
        """
        try:
            # データ読み込み
            page_data = await self.page_repo.get_page(page_id)
            if not page_data:
                raise VectorizerError(f"Page not found: {page_id}")

            jina_data = await self.file_repo.load_json_file(page_id)
            content = jina_data["data"]["content"]

            # チャンキング
            chunks = self.text_chunker.chunk_text(content)
            if not chunks:
                raise VectorizerError("No chunks generated from content")

            # Weaviate保存
            weaviate_id = await self._save_chunks_to_weaviate(page_data, chunks)

            # ページにWeaviate ID保存
            await self.page_repo.update_weaviate_id(page_id, weaviate_id)

        except Exception as e:
            raise VectorizerError(f"Vectorization error: {str(e)}")

    async def _save_chunks_to_weaviate(self, page_data, chunks: list[str]) -> str:
        """チャンクをWeaviateに保存.

        Args:
            page_data: ページデータ
            chunks: チャンクリスト

        Returns:
            最初のチャンクのWeaviate ID
        """
        first_chunk_id = None

        try:
            for i, chunk in enumerate(chunks):
                weaviate_object = {
                    "pageId": page_data.id,
                    "chunkId": i,
                    "url": page_data.url,
                    "title": page_data.title,
                    "memo": page_data.memo or "",
                    "content": chunk,
                    "summary": page_data.summary or "",
                    "keywords": json.loads(page_data.keywords or "[]"),
                    "createdAt": page_data.created_at.isoformat(),
                }

                result = self.client.data_object.create(
                    data_object=weaviate_object, class_name="GrimoireChunk"
                )

                if i == 0:
                    first_chunk_id = result

            return first_chunk_id

        except Exception as e:
            raise VectorizerError(f"Failed to save chunks to Weaviate: {str(e)}")

    async def health_check(self) -> bool:
        """Weaviateヘルスチェック.

        Returns:
            Weaviateが利用可能かどうか
        """
        try:
            self.client.schema.get()
            return True
        except Exception:
            return False

    async def ensure_schema(self) -> None:
        """Weaviateスキーマ確保.

        Raises:
            VectorizerError: スキーマ作成エラー
        """
        try:
            # 既存スキーマ確認
            existing_classes = self.client.schema.get()["classes"]
            class_names = [cls["class"] for cls in existing_classes]

            if "GrimoireChunk" not in class_names:
                # スキーマ作成
                schema = {
                    "class": "GrimoireChunk",
                    "description": "Grimoire Keeperで管理するWebページのチャンク",
                    "properties": [
                        {"name": "pageId", "dataType": ["int"]},
                        {"name": "chunkId", "dataType": ["int"]},
                        {"name": "url", "dataType": ["text"]},
                        {"name": "title", "dataType": ["text"]},
                        {"name": "memo", "dataType": ["text"]},
                        {"name": "content", "dataType": ["text"]},
                        {"name": "summary", "dataType": ["text"]},
                        {"name": "keywords", "dataType": ["text[]"]},
                        {"name": "createdAt", "dataType": ["date"]},
                    ],
                    "vectorizer": "text2vec-openai",
                }
                self.client.schema.create_class(schema)

        except Exception as e:
            raise VectorizerError(f"Failed to ensure schema: {str(e)}")
