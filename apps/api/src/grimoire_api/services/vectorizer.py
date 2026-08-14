"""Vectorization service for Weaviate."""

import asyncio
import logging
from typing import Any

import weaviate
from pydantic import ValidationError
from weaviate.classes.config import Configure, DataType, Property
from weaviate.classes.query import Filter
from weaviate.util import generate_uuid5

from ..config import settings
from ..models.database import Page, ProcessingStep
from ..models.external import FetchedDocument
from ..repositories.file_repository import FileRepository
from ..repositories.page_repository import PageRepository
from ..utils.exceptions import VectorizerError
from .chunking_service import ChunkingService

logger = logging.getLogger(__name__)


def _insert_objects_sync(
    collection: Any, objects_to_insert: list[tuple[dict[str, Any], Any]]
) -> None:
    """Weaviateオブジェクトを同期的に挿入する."""
    for properties, object_uuid in objects_to_insert:
        collection.data.insert(properties=properties, uuid=object_uuid)


class VectorizerService:
    """ページ代表データと本文チャンクを分離して保存する."""

    def __init__(
        self,
        page_repo: PageRepository,
        file_repo: FileRepository,
        chunking_service: ChunkingService,
        weaviate_client: weaviate.WeaviateClient,
    ):
        self.page_repo = page_repo
        self.file_repo = file_repo
        self.chunking_service = chunking_service
        self.weaviate_client = weaviate_client

    async def vectorize_content(self, page_id: int) -> None:
        """ページを索引化し、SQLiteのWeaviate IDと処理ステップを更新する."""
        try:
            page_data, chunks = await self._load_page_and_chunks(page_id)
            weaviate_id = await self._save_page_to_weaviate(page_data, chunks)
            await self.page_repo.update_weaviate_id_and_step(
                page_id, weaviate_id, ProcessingStep.VECTORIZED
            )
        except Exception as e:
            raise VectorizerError(f"Vectorization error: {str(e)}")

    async def reindex_content(self, page_id: int) -> str:
        """処理状態を変更せず、保存済みデータからページを再索引化する."""
        try:
            page_data, chunks = await self._load_page_and_chunks(page_id)
            return await self._save_page_to_weaviate(page_data, chunks)
        except Exception as e:
            raise VectorizerError(f"Reindex error: {str(e)}")

    async def _load_page_and_chunks(self, page_id: int) -> tuple[Page, list[str]]:
        page_data = await self.page_repo.get_page(page_id)
        if not page_data:
            raise VectorizerError(f"Page not found: {page_id}")

        raw_jina_data = await self.file_repo.load_json_file(page_id)
        try:
            document = FetchedDocument.from_jina_response(
                raw_jina_data, source_url=page_data.url
            )
        except (ValidationError, ValueError, TypeError):
            raise VectorizerError(
                f"invalid stored Jina response for page_id={page_id}"
            ) from None

        chunks = self.chunking_service.chunk_document(document)
        if not chunks:
            raise VectorizerError("No chunks generated from content")
        return page_data, chunks

    async def _save_page_to_weaviate(self, page_data: Page, chunks: list[str]) -> str:
        """ページ代表オブジェクト1件と本文チャンクを別コレクションへ保存する."""
        if page_data.id is None:
            raise VectorizerError("Page ID is required")

        try:
            page_collection = self.weaviate_client.collections.get(
                settings.WEAVIATE_PAGE_COLLECTION_NAME
            )
            chunk_collection = self.weaviate_client.collections.get(
                settings.WEAVIATE_CHUNK_COLLECTION_NAME
            )

            await self._delete_existing_objects(page_collection, page_data.id)
            await self._delete_existing_objects(chunk_collection, page_data.id)

            page_uuid = generate_uuid5(f"page-{page_data.id}")
            created_at = self._format_created_at(page_data)
            page_properties = {
                "pageId": page_data.id,
                "url": page_data.url,
                "title": page_data.title,
                "memo": page_data.memo or "",
                "summary": page_data.summary or "",
                "keywords": page_data.keywords or [],
                "createdAt": created_at,
            }
            await asyncio.to_thread(
                _insert_objects_sync,
                page_collection,
                [(page_properties, page_uuid)],
            )

            chunk_objects = [
                (
                    {
                        "pageId": page_data.id,
                        "chunkId": chunk_id,
                        "content": content,
                    },
                    generate_uuid5(f"chunk-{page_data.id}-{chunk_id}"),
                )
                for chunk_id, content in enumerate(chunks)
            ]
            await asyncio.to_thread(
                _insert_objects_sync, chunk_collection, chunk_objects
            )
            return str(page_uuid)
        except Exception as e:
            raise VectorizerError(f"Failed to save page to Weaviate: {str(e)}")

    async def delete_page_from_index(self, page_id: int) -> None:
        """再構築先のページ代表・本文チャンクをページID単位で削除する."""
        try:
            page_collection = self.weaviate_client.collections.get(
                settings.WEAVIATE_PAGE_COLLECTION_NAME
            )
            chunk_collection = self.weaviate_client.collections.get(
                settings.WEAVIATE_CHUNK_COLLECTION_NAME
            )
            await self._delete_existing_objects(page_collection, page_id)
            await self._delete_existing_objects(chunk_collection, page_id)
        except Exception as e:
            raise VectorizerError(
                f"Failed to remove page {page_id} from Weaviate: {str(e)}"
            ) from e

    async def _save_chunks_to_weaviate(self, page_data: Page, chunks: list[str]) -> str:
        """後方互換用の内部エイリアス."""
        return await self._save_page_to_weaviate(page_data, chunks)

    @staticmethod
    def _format_created_at(page_data: Page) -> str:
        if page_data.created_at.tzinfo is None:
            return page_data.created_at.replace(tzinfo=None).isoformat() + "Z"
        return page_data.created_at.isoformat()

    async def _delete_existing_objects(self, collection: Any, page_id: int) -> None:
        """対象ページの既存オブジェクトを削除し、削除完了を確認する."""
        try:
            result = await asyncio.to_thread(
                collection.data.delete_many,
                where=Filter.by_property("pageId").equal(page_id),
            )
            if hasattr(result, "matches"):
                logger.info("Deleted %d objects for page %d", result.matches, page_id)
            if hasattr(result, "failed") and result.failed > 0:
                logger.warning(
                    "Failed to delete %d objects for page %d", result.failed, page_id
                )
            if not hasattr(result, "matches") or result.matches == 0:
                return

            for attempt in range(10):
                await asyncio.sleep(0.1)
                remaining = await asyncio.to_thread(
                    collection.query.fetch_objects,
                    filters=Filter.by_property("pageId").equal(page_id),
                    limit=1,
                )
                if not remaining.objects:
                    return
                logger.debug(
                    "Waiting for deletion for page %d (attempt %d/10)",
                    page_id,
                    attempt + 1,
                )
            raise VectorizerError(
                f"Deletion of objects for page {page_id} "
                "did not complete within timeout"
            )
        except VectorizerError:
            raise
        except Exception as e:
            logger.error("Failed to delete objects for page %d: %s", page_id, e)
            raise

    async def _delete_existing_chunks(self, collection: Any, page_id: int) -> None:
        """後方互換用の内部エイリアス."""
        await self._delete_existing_objects(collection, page_id)

    async def health_check(self) -> bool:
        try:
            self.weaviate_client.is_ready()
            return True
        except Exception:
            return False

    async def ensure_schema(self) -> None:
        """ページ用・本文チャンク用のWeaviateスキーマを作成する."""
        try:
            if not self.weaviate_client.collections.exists(
                settings.WEAVIATE_PAGE_COLLECTION_NAME
            ):
                self.weaviate_client.collections.create(
                    name=settings.WEAVIATE_PAGE_COLLECTION_NAME,
                    description="Grimoire Keeperのページ代表検索データ",
                    properties=[
                        Property(name="pageId", data_type=DataType.INT),
                        Property(name="url", data_type=DataType.TEXT),
                        Property(name="title", data_type=DataType.TEXT),
                        Property(name="memo", data_type=DataType.TEXT),
                        Property(name="summary", data_type=DataType.TEXT),
                        Property(name="keywords", data_type=DataType.TEXT_ARRAY),
                        Property(name="createdAt", data_type=DataType.DATE),
                    ],
                    vector_config=[
                        Configure.Vectors.text2vec_openai(
                            name="title_vector",
                            source_properties=["title", "summary"],
                        ),
                        Configure.Vectors.text2vec_openai(
                            name="memo_vector", source_properties=["memo"]
                        ),
                    ],
                )

            if not self.weaviate_client.collections.exists(
                settings.WEAVIATE_CHUNK_COLLECTION_NAME
            ):
                self.weaviate_client.collections.create(
                    name=settings.WEAVIATE_CHUNK_COLLECTION_NAME,
                    description="Grimoire Keeperの本文チャンク",
                    properties=[
                        Property(name="pageId", data_type=DataType.INT),
                        Property(name="chunkId", data_type=DataType.INT),
                        Property(name="content", data_type=DataType.TEXT),
                    ],
                    vector_config=[
                        Configure.Vectors.text2vec_openai(
                            name="content_vector", source_properties=["content"]
                        )
                    ],
                )
        except Exception as e:
            raise VectorizerError(f"Failed to ensure schema: {str(e)}")
