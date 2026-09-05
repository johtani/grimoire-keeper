"""Vectorization service for Weaviate."""

import asyncio
import json
import logging
from enum import Enum
from time import monotonic
from typing import Any, NoReturn

import weaviate
from pydantic import ValidationError
from weaviate.classes.config import Configure, DataType, Property
from weaviate.classes.query import Filter
from weaviate.exceptions import (
    WeaviateConnectionError,
    WeaviateGRPCUnavailableError,
    WeaviateRetryError,
    WeaviateTimeoutError,
)
from weaviate.util import generate_uuid5

from ..config import settings
from ..models.database import Page, ProcessingStep
from ..models.external import FetchedDocument
from ..repositories.file_repository import FileRepository
from ..repositories.page_repository import PageRepository
from ..utils.datetime import utc_isoformat
from ..utils.exceptions import VectorizerError
from ..utils.retry import RetryPolicy, retry_external_call
from .chunking_service import ChunkingService

logger = logging.getLogger(__name__)

EXPECTED_NAMED_VECTORS = {
    "page": {"title_vector", "memo_vector"},
    "chunk": {"content_vector"},
}
EXPECTED_PROPERTIES = {
    "page": {
        "pageId": DataType.INT,
        "url": DataType.TEXT,
        "title": DataType.TEXT,
        "memo": DataType.TEXT,
        "summary": DataType.TEXT,
        "keywords": DataType.TEXT_ARRAY,
        "createdAt": DataType.DATE,
    },
    "chunk": {
        "pageId": DataType.INT,
        "chunkId": DataType.INT,
        "content": DataType.TEXT,
    },
}


def _raise_incompatible_schema(collection_name: str, detail: str) -> NoReturn:
    raise VectorizerError(
        f"Incompatible Weaviate schema for {collection_name}: {detail}. "
        "Recreate the collections and run scripts/reindex_weaviate.py."
    )


def _validate_collection_schema(
    client: weaviate.WeaviateClient,
    collection_name: str,
    expected_properties: dict[str, DataType],
    expected_vector_names: set[str],
) -> None:
    """Reject a collection whose properties or vectors are incompatible."""
    config = client.collections.get(collection_name).config.get()
    actual_properties = {prop.name: prop.data_type for prop in config.properties}
    for property_name, expected_type in expected_properties.items():
        actual_type = actual_properties.get(property_name)
        if actual_type is None:
            _raise_incompatible_schema(
                collection_name, f"required property {property_name!r} is missing"
            )
        if actual_type != expected_type:
            _raise_incompatible_schema(
                collection_name,
                f"property {property_name!r} type is {actual_type.value!r}, "
                f"expected {expected_type.value!r}",
            )

    vector_config = config.vector_config
    if vector_config is None:
        _raise_incompatible_schema(
            collection_name, "named vector configuration is missing"
        )
    actual_names = set(vector_config)
    if actual_names != expected_vector_names:
        _raise_incompatible_schema(
            collection_name,
            f"named vectors are {sorted(actual_names)}, expected "
            f"{sorted(expected_vector_names)}",
        )

    for vector_name in sorted(expected_vector_names):
        vectorizer = vector_config[vector_name].vectorizer
        provider = vectorizer.vectorizer
        if isinstance(provider, Enum):
            provider = provider.value
        model_config = dict(vectorizer.model)
        actual_model = model_config.get("model")
        actual_dimensions = model_config.get("dimensions")
        if provider != settings.WEAVIATE_EMBEDDING_PROVIDER:
            _raise_incompatible_schema(
                collection_name,
                f"{vector_name} provider is {provider!r}, expected "
                f"{settings.WEAVIATE_EMBEDDING_PROVIDER!r}",
            )
        if actual_model != settings.WEAVIATE_EMBEDDING_MODEL:
            _raise_incompatible_schema(
                collection_name,
                f"{vector_name} model is {actual_model!r}, expected "
                f"{settings.WEAVIATE_EMBEDDING_MODEL!r}",
            )
        if actual_dimensions != settings.WEAVIATE_EMBEDDING_DIMENSIONS:
            _raise_incompatible_schema(
                collection_name,
                f"{vector_name} dimensions are {actual_dimensions!r}, expected "
                f"{settings.WEAVIATE_EMBEDDING_DIMENSIONS!r}",
            )


def validate_weaviate_schema(client: weaviate.WeaviateClient) -> None:
    """Validate all collections required by registration and search."""
    schemas = (
        (
            "page",
            settings.WEAVIATE_PAGE_COLLECTION_NAME,
        ),
        (
            "chunk",
            settings.WEAVIATE_CHUNK_COLLECTION_NAME,
        ),
    )
    for schema_name, collection_name in schemas:
        if not client.collections.exists(collection_name):
            _raise_incompatible_schema(collection_name, "collection is missing")
        _validate_collection_schema(
            client,
            collection_name,
            EXPECTED_PROPERTIES[schema_name],
            EXPECTED_NAMED_VECTORS[schema_name],
        )


def _insert_objects_sync(
    collection: Any,
    objects_to_insert: list[tuple[dict[str, Any], Any]],
    *,
    max_objects: int,
    max_bytes: int,
    concurrent_requests: int,
) -> None:
    """Weaviateオブジェクトをバッチ挿入し、個別エラーを検査する."""
    batches: list[list[tuple[dict[str, Any], Any]]] = []
    batch_sizes: list[int] = []
    current_batch: list[tuple[dict[str, Any], Any]] = []
    current_size = 0

    for properties, object_uuid in objects_to_insert:
        object_size = len(
            json.dumps(
                {"properties": properties, "uuid": str(object_uuid)},
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        if object_size > max_bytes:
            raise VectorizerError(
                "Weaviate object exceeds batch byte limit: "
                f"page_id={properties.get('pageId')}, uuid={object_uuid}, "
                f"estimated_bytes={object_size}, max_bytes={max_bytes}"
            )
        if current_batch and (
            len(current_batch) >= max_objects or current_size + object_size > max_bytes
        ):
            batches.append(current_batch)
            batch_sizes.append(current_size)
            current_batch = []
            current_size = 0
        current_batch.append((properties, object_uuid))
        current_size += object_size

    if current_batch:
        batches.append(current_batch)
        batch_sizes.append(current_size)

    for batch_number, (objects, estimated_bytes) in enumerate(
        zip(batches, batch_sizes, strict=True), start=1
    ):
        logger.info(
            "Sending Weaviate batch %d/%d: objects=%d estimated_bytes=%d",
            batch_number,
            len(batches),
            len(objects),
            estimated_bytes,
        )
        with collection.batch.fixed_size(
            batch_size=len(objects), concurrent_requests=concurrent_requests
        ) as batch:
            for properties, object_uuid in objects:
                batch.add_object(properties=properties, uuid=object_uuid)

        failed_objects = collection.batch.failed_objects
        if failed_objects:
            messages = "; ".join(str(failure.message) for failure in failed_objects)
            raise VectorizerError(
                f"Failed to insert {len(failed_objects)} Weaviate objects: {messages}"
            )


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
        self._retry_policy = RetryPolicy(
            attempts=settings.WEAVIATE_RETRY_ATTEMPTS,
            backoff_base=settings.WEAVIATE_RETRY_BACKOFF_BASE,
            backoff_max=settings.WEAVIATE_RETRY_BACKOFF_MAX,
            jitter=settings.WEAVIATE_RETRY_JITTER,
            retry_after_max=settings.WEAVIATE_RETRY_AFTER_MAX,
        )

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
        return await retry_external_call(
            lambda: self._save_page_once(page_data, chunks),
            service="weaviate",
            operation_name="save_page",
            policy=self._retry_policy,
            classify_error=self._classify_error,
        )

    async def _save_page_once(self, page_data: Page, chunks: list[str]) -> str:
        """Perform one idempotent page-save attempt."""
        if page_data.id is None:
            raise VectorizerError("Page ID is required")

        try:
            page_collection = self.weaviate_client.collections.get(
                settings.WEAVIATE_PAGE_COLLECTION_NAME
            )
            chunk_collection = self.weaviate_client.collections.get(
                settings.WEAVIATE_CHUNK_COLLECTION_NAME
            )
        except Exception as e:
            raise VectorizerError(f"Failed to save page to Weaviate: {str(e)}") from e

        try:
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
                max_objects=settings.WEAVIATE_BATCH_MAX_OBJECTS,
                max_bytes=settings.WEAVIATE_BATCH_MAX_BYTES,
                concurrent_requests=settings.WEAVIATE_BATCH_CONCURRENCY,
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
                _insert_objects_sync,
                chunk_collection,
                chunk_objects,
                max_objects=settings.WEAVIATE_BATCH_MAX_OBJECTS,
                max_bytes=settings.WEAVIATE_BATCH_MAX_BYTES,
                concurrent_requests=settings.WEAVIATE_BATCH_CONCURRENCY,
            )
            return str(page_uuid)
        except Exception as e:
            cleanup_errors = await self._cleanup_failed_save(
                page_collection, chunk_collection, page_data.id
            )
            message = f"Failed to save page to Weaviate: {str(e)}"
            if cleanup_errors:
                message += f"; cleanup failed: {'; '.join(cleanup_errors)}"
            raise VectorizerError(message) from e

    async def _cleanup_failed_save(
        self, page_collection: Any, chunk_collection: Any, page_id: int
    ) -> list[str]:
        """保存失敗後、両コレクションから対象ページの部分登録を除去する."""
        errors: list[str] = []
        for collection_name, collection in (
            ("page", page_collection),
            ("chunk", chunk_collection),
        ):
            try:
                await self._delete_existing_objects(collection, page_id)
            except Exception as cleanup_error:
                logger.error(
                    "Failed to clean up %s objects for page %d: %s",
                    collection_name,
                    page_id,
                    cleanup_error,
                )
                errors.append(f"{collection_name}: {cleanup_error}")
        return errors

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
        return utc_isoformat(page_data.created_at)

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
                raise VectorizerError(
                    f"Failed to delete {result.failed} objects for page {page_id}"
                )
            if not hasattr(result, "matches") or result.matches == 0:
                return

            started_at = monotonic()
            deadline = started_at + settings.WEAVIATE_DELETE_TIMEOUT
            attempt = 0
            while monotonic() < deadline:
                remaining_time = deadline - monotonic()
                await asyncio.sleep(
                    min(settings.WEAVIATE_DELETE_POLL_INTERVAL, remaining_time)
                )
                attempt += 1
                remaining = await asyncio.to_thread(
                    collection.query.fetch_objects,
                    filters=Filter.by_property("pageId").equal(page_id),
                    limit=1,
                )
                if not remaining.objects:
                    return
                logger.debug(
                    "Waiting for deletion for page %d "
                    "(attempt=%d interval=%.3fs timeout=%.3fs condition=pageId==%d)",
                    page_id,
                    attempt,
                    settings.WEAVIATE_DELETE_POLL_INTERVAL,
                    settings.WEAVIATE_DELETE_TIMEOUT,
                    page_id,
                )
            message = (
                f"Deletion of objects for page {page_id} did not complete within "
                f"timeout={settings.WEAVIATE_DELETE_TIMEOUT}s "
                f"(poll_interval={settings.WEAVIATE_DELETE_POLL_INTERVAL}s, "
                f"condition=pageId=={page_id})"
            )
            logger.error(message)
            raise VectorizerError(message)
        except VectorizerError:
            raise
        except Exception as e:
            logger.error("Failed to delete objects for page %d: %s", page_id, e)
            raise

    @staticmethod
    def _classify_error(error: Exception) -> tuple[bool, str, float | None]:
        """Classify nested Weaviate SDK errors while keeping messages private."""
        current: BaseException | None = error
        while current is not None:
            if isinstance(current, (TimeoutError, WeaviateTimeoutError)):
                return True, "timeout", None
            if isinstance(
                current,
                (
                    OSError,
                    WeaviateConnectionError,
                    WeaviateGRPCUnavailableError,
                    WeaviateRetryError,
                ),
            ):
                return True, "connection", None
            current = current.__cause__
        return False, "permanent", None

    async def _delete_existing_chunks(self, collection: Any, page_id: int) -> None:
        """後方互換用の内部エイリアス."""
        await self._delete_existing_objects(collection, page_id)

    async def health_check(self) -> bool:
        try:
            self.weaviate_client.is_ready()
            return True
        except Exception:
            return False

    async def is_page_registered(self, page_id: int) -> bool:
        """ページ代表オブジェクトがWeaviateに存在するか確認する."""
        collection = self.weaviate_client.collections.get(
            settings.WEAVIATE_PAGE_COLLECTION_NAME
        )
        response = await asyncio.to_thread(
            collection.query.fetch_objects,
            filters=Filter.by_property("pageId").equal(page_id),
            limit=1,
        )
        return bool(response.objects)

    async def ensure_schema(self) -> None:
        """ページ用・本文チャンク用スキーマを作成し、互換性を検証する."""
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
                            model=settings.WEAVIATE_EMBEDDING_MODEL,
                            dimensions=settings.WEAVIATE_EMBEDDING_DIMENSIONS,
                        ),
                        Configure.Vectors.text2vec_openai(
                            name="memo_vector",
                            source_properties=["memo"],
                            model=settings.WEAVIATE_EMBEDDING_MODEL,
                            dimensions=settings.WEAVIATE_EMBEDDING_DIMENSIONS,
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
                            name="content_vector",
                            source_properties=["content"],
                            model=settings.WEAVIATE_EMBEDDING_MODEL,
                            dimensions=settings.WEAVIATE_EMBEDDING_DIMENSIONS,
                        )
                    ],
                )

            self._validate_collection_schema(
                settings.WEAVIATE_PAGE_COLLECTION_NAME,
                EXPECTED_PROPERTIES["page"],
                EXPECTED_NAMED_VECTORS["page"],
            )
            self._validate_collection_schema(
                settings.WEAVIATE_CHUNK_COLLECTION_NAME,
                EXPECTED_PROPERTIES["chunk"],
                EXPECTED_NAMED_VECTORS["chunk"],
            )
        except Exception as e:
            raise VectorizerError(f"Failed to ensure schema: {str(e)}")

    def _validate_collection_schema(
        self,
        collection_name: str,
        expected_properties: dict[str, DataType],
        expected_vector_names: set[str],
    ) -> None:
        _validate_collection_schema(
            self.weaviate_client,
            collection_name,
            expected_properties,
            expected_vector_names,
        )
