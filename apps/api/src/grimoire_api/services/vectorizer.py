"""Vectorization service for Weaviate."""

import asyncio
import logging
from typing import Any

import weaviate
from weaviate.classes.config import Configure, DataType, Property
from weaviate.classes.query import Filter
from weaviate.util import generate_uuid5

from ..config import settings
from ..models.database import ProcessingStep
from ..repositories.file_repository import FileRepository
from ..repositories.page_repository import PageRepository
from ..utils.exceptions import VectorizerError
from .chunking_service import ChunkingService

logger = logging.getLogger(__name__)


def _insert_chunks_sync(
    collection: Any, objects_to_insert: list[tuple[dict, Any]]
) -> None:
    """チャンクを同期的にWeaviateに挿入する (asyncio.to_thread から呼び出す).

    Args:
        collection: Weaviateコレクション
        objects_to_insert: (weaviate_object, chunk_uuid) のリスト
    """
    for weaviate_object, chunk_uuid in objects_to_insert:
        collection.data.insert(properties=weaviate_object, uuid=chunk_uuid)


class VectorizerService:
    """ベクトル化サービス."""

    def __init__(
        self,
        page_repo: PageRepository,
        file_repo: FileRepository,
        chunking_service: ChunkingService,
        weaviate_client: weaviate.WeaviateClient,
    ):
        """初期化.

        Args:
            page_repo: ページリポジトリ
            file_repo: ファイルリポジトリ
            chunking_service: チャンキングサービス
            weaviate_client: Weaviateクライアント (共有インスタンス)
        """
        self.page_repo = page_repo
        self.file_repo = file_repo
        self.chunking_service = chunking_service
        self.weaviate_client = weaviate_client

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

            # チャンキング（言語情報を使用）
            chunks = self.chunking_service.chunk_text_with_jina_data(content, jina_data)
            if not chunks:
                raise VectorizerError("No chunks generated from content")

            # Weaviate保存
            weaviate_id = await self._save_chunks_to_weaviate(page_data, chunks)

            # ページにWeaviate IDと成功ステップをアトミックに保存
            await self.page_repo.update_weaviate_id_and_step(
                page_id, weaviate_id, ProcessingStep.VECTORIZED
            )

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
            collection = self.weaviate_client.collections.get(
                settings.WEAVIATE_COLLECTION_NAME
            )

            # 既存データを削除
            await self._delete_existing_chunks(collection, page_data.id)

            # 挿入オブジェクトリストを構築
            objects_to_insert: list[tuple[dict, Any]] = []
            for i, chunk in enumerate(chunks):
                weaviate_object = {
                    "pageId": page_data.id,
                    "chunkId": i,
                    "url": page_data.url,
                    "title": page_data.title,
                    "memo": page_data.memo or "",
                    "content": chunk,
                    "summary": page_data.summary or "",
                    "keywords": page_data.keywords,
                    "createdAt": (
                        page_data.created_at.replace(tzinfo=None).isoformat() + "Z"
                        if page_data.created_at.tzinfo is None
                        else page_data.created_at.isoformat()
                    ),
                    "isSummary": i == 0,
                }
                # UUID生成: pageId-chunkIdの文字列からUUID5を生成
                uuid_source = f"{page_data.id}-{i}"
                chunk_uuid = generate_uuid5(uuid_source)
                objects_to_insert.append((weaviate_object, chunk_uuid))
                if i == 0:
                    first_chunk_id = str(chunk_uuid)

            # 同期 insert をスレッドプールで実行してイベントループをブロックしない
            await asyncio.to_thread(_insert_chunks_sync, collection, objects_to_insert)

            return first_chunk_id or ""

        except Exception as e:
            raise VectorizerError(f"Failed to save chunks to Weaviate: {str(e)}")

    async def _delete_existing_chunks(self, collection: Any, page_id: int) -> None:
        """既存チャンクを削除し、削除完了を確認する.

        Args:
            collection: Weaviateコレクション
            page_id: ページID

        Raises:
            VectorizerError: 削除がタイムアウトした場合
        """
        try:
            result = await asyncio.to_thread(
                collection.data.delete_many,
                where=Filter.by_property("pageId").equal(page_id),
            )
            if hasattr(result, "matches"):
                logger.info("Deleted %d chunks for page %d", result.matches, page_id)
            if hasattr(result, "failed") and result.failed > 0:
                logger.warning(
                    "Failed to delete %d chunks for page %d", result.failed, page_id
                )

            # 削除対象がなければ確認不要
            if not hasattr(result, "matches") or result.matches == 0:
                return

            # 削除完了をポーリングで確認 (sleep → check の順で一貫性を保つ)
            max_retries = 10
            wait_sec = 0.1
            for attempt in range(max_retries):
                await asyncio.sleep(wait_sec)
                remaining = await asyncio.to_thread(
                    collection.query.fetch_objects,
                    filters=Filter.by_property("pageId").equal(page_id),
                    limit=1,
                )
                if not remaining.objects:
                    return
                logger.debug(
                    "Waiting for deletion of chunks for page %d (attempt %d/%d)",
                    page_id,
                    attempt + 1,
                    max_retries,
                )

            raise VectorizerError(
                f"Deletion of chunks for page {page_id} did not complete within timeout"
            )
        except VectorizerError:
            raise
        except Exception as e:
            logger.error("Failed to delete existing chunks for page %d: %s", page_id, e)
            raise

    async def health_check(self) -> bool:
        """Weaviateヘルスチェック.

        Returns:
            Weaviateが利用可能かどうか
        """
        try:
            self.weaviate_client.is_ready()
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
            if not self.weaviate_client.collections.exists(
                settings.WEAVIATE_COLLECTION_NAME
            ):
                # コレクション作成
                self.weaviate_client.collections.create(
                    name=settings.WEAVIATE_COLLECTION_NAME,
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
                        Property(name="isSummary", data_type=DataType.BOOL),
                    ],
                    vector_config=[
                        Configure.Vectors.text2vec_openai(
                            name="content_vector", source_properties=["content"]
                        ),
                        Configure.Vectors.text2vec_openai(
                            name="title_vector",
                            source_properties=["title", "summary"],
                        ),
                        Configure.Vectors.text2vec_openai(
                            name="memo_vector", source_properties=["memo"]
                        ),
                    ],
                )

        except Exception as e:
            raise VectorizerError(f"Failed to ensure schema: {str(e)}")
