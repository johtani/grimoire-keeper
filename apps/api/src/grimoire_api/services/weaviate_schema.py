"""Weaviate schema creation and compatibility validation."""

import asyncio
from enum import Enum
from typing import NoReturn

import weaviate
from weaviate.classes.config import Configure, DataType, Property

from ..config import settings
from ..utils.exceptions import WeaviateSchemaError

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
    raise WeaviateSchemaError(
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


class WeaviateSchemaService:
    """Create and validate the Weaviate collections used by the application."""

    def __init__(self, client: weaviate.WeaviateClient) -> None:
        self.client = client

    async def health_check(self) -> bool:
        """Return whether Weaviate is ready to accept requests."""
        try:
            return await asyncio.to_thread(self.client.is_ready)
        except Exception:
            return False

    def validate(self) -> None:
        """Validate all collections required by registration and search."""
        schemas = (
            ("page", settings.WEAVIATE_PAGE_COLLECTION_NAME),
            ("chunk", settings.WEAVIATE_CHUNK_COLLECTION_NAME),
        )
        for schema_name, collection_name in schemas:
            if not self.client.collections.exists(collection_name):
                _raise_incompatible_schema(collection_name, "collection is missing")
            _validate_collection_schema(
                self.client,
                collection_name,
                EXPECTED_PROPERTIES[schema_name],
                EXPECTED_NAMED_VECTORS[schema_name],
            )

    async def ensure_schema(self) -> None:
        """Create missing collections and validate their compatibility."""
        try:
            if not self.client.collections.exists(
                settings.WEAVIATE_PAGE_COLLECTION_NAME
            ):
                self.client.collections.create(
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

            if not self.client.collections.exists(
                settings.WEAVIATE_CHUNK_COLLECTION_NAME
            ):
                self.client.collections.create(
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

            _validate_collection_schema(
                self.client,
                settings.WEAVIATE_PAGE_COLLECTION_NAME,
                EXPECTED_PROPERTIES["page"],
                EXPECTED_NAMED_VECTORS["page"],
            )
            _validate_collection_schema(
                self.client,
                settings.WEAVIATE_CHUNK_COLLECTION_NAME,
                EXPECTED_PROPERTIES["chunk"],
                EXPECTED_NAMED_VECTORS["chunk"],
            )
        except WeaviateSchemaError:
            raise
        except Exception as error:
            raise WeaviateSchemaError(f"Failed to ensure schema: {error}") from error
