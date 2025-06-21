"""Vectorization service for Weaviate."""

import json
from typing import Any

import weaviate
from weaviate.classes.config import Configure, DataType, Property

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
        weaviate_url: str | None = None,
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
    def client(self) -> weaviate.WeaviateClient:
        """Weaviateクライアント."""
        if self._client is None:
            host = self.weaviate_url.replace("http://", "").replace(":8080", "")
            self._client = weaviate.connect_to_local(host=host)
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

    async def _save_chunks_to_weaviate(self, page_data: Any, chunks: list[str]) -> str:
        """チャンクをWeaviateに保存.

        Args:
            page_data: ページデータ
            chunks: チャンクリスト

        Returns:
            最初のチャンクのWeaviate ID
        """
        first_chunk_id = None

        try:
            collection = self.client.collections.get("GrimoireChunk")

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
                    "createdAt": page_data.created_at,
                }

                result = collection.data.insert(properties=weaviate_object)

                if i == 0:
                    first_chunk_id = str(result)

            return first_chunk_id or ""

        except Exception as e:
            raise VectorizerError(f"Failed to save chunks to Weaviate: {str(e)}")

    async def health_check(self) -> bool:
        """Weaviateヘルスチェック.

        Returns:
            Weaviateが利用可能かどうか
        """
        try:
            self.client.is_ready()
            return True
        except Exception:
            return False

    async def ensure_schema(self) -> None:
        """Weaviateスキーマ確保.

        Raises:
            VectorizerError: スキーマ作成エラー
        """
        try:
            # 既存コレクション確認
            if not self.client.collections.exists("GrimoireChunk"):
                # コレクション作成
                self.client.collections.create(
                    name="GrimoireChunk",
                    description="Grimoire Keeperで管理するWebページのチャンク",
                    properties=[
                        Property(name="pageId", data_type=DataType.INT),
                        Property(name="chunkId", data_type=DataType.INT),
                        Property(name="url", data_type=DataType.TEXT),
                        Property(name="title", data_type=DataType.TEXT),
                        Property(name="memo", data_type=DataType.TEXT),
                        Property(name="content", data_type=DataType.TEXT),
                        Property(name="summary", data_type=DataType.TEXT),
                        Property(name="keywords", data_type=DataType.TEXT_ARRAY),
                        Property(name="createdAt", data_type=DataType.DATE),
                    ],
                    vectorizer_config=Configure.Vectorizer.text2vec_openai(),
                )

        except Exception as e:
            raise VectorizerError(f"Failed to ensure schema: {str(e)}")
