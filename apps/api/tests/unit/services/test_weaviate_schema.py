"""Tests for Weaviate schema management."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from grimoire_api.config import settings
from grimoire_api.services.weaviate_schema import (
    EXPECTED_PROPERTIES,
    WeaviateSchemaService,
)
from grimoire_api.utils.exceptions import WeaviateSchemaError
from weaviate.classes.config import DataType


@pytest.fixture
def schema_dependencies() -> dict[str, MagicMock]:
    """Return a client with compatible page and chunk collection configs."""

    def schema_config(schema_name: str, *vector_names: str) -> SimpleNamespace:
        vector_config = {
            name: SimpleNamespace(
                vectorizer=SimpleNamespace(
                    vectorizer="text2vec-openai",
                    model={
                        "model": settings.WEAVIATE_EMBEDDING_MODEL,
                        "dimensions": settings.WEAVIATE_EMBEDDING_DIMENSIONS,
                    },
                )
            )
            for name in vector_names
        }
        properties = [
            SimpleNamespace(name=name, data_type=data_type)
            for name, data_type in EXPECTED_PROPERTIES[schema_name].items()
        ]
        return SimpleNamespace(properties=properties, vector_config=vector_config)

    page_collection = MagicMock()
    page_collection.config.get.return_value = schema_config(
        "page", "title_vector", "memo_vector"
    )
    chunk_collection = MagicMock()
    chunk_collection.config.get.return_value = schema_config("chunk", "content_vector")
    client = MagicMock()
    client.collections.exists.return_value = True
    client.collections.get.side_effect = lambda name: (
        page_collection
        if name == settings.WEAVIATE_PAGE_COLLECTION_NAME
        else chunk_collection
    )
    return {
        "client": client,
        "page_collection": page_collection,
        "chunk_collection": chunk_collection,
    }


@pytest.mark.parametrize(("ready", "expected"), [(True, True), (False, False)])
async def test_health_check_reflects_client_readiness(
    schema_dependencies: dict[str, MagicMock], ready: bool, expected: bool
) -> None:
    client = schema_dependencies["client"]
    client.is_ready.return_value = ready

    assert await WeaviateSchemaService(client).health_check() is expected


async def test_health_check_returns_false_on_failure(
    schema_dependencies: dict[str, MagicMock],
) -> None:
    client = schema_dependencies["client"]
    client.is_ready.side_effect = RuntimeError("connection failed")

    assert await WeaviateSchemaService(client).health_check() is False


async def test_ensure_schema_creates_both_collections(
    schema_dependencies: dict[str, MagicMock],
) -> None:
    client = schema_dependencies["client"]
    client.collections.exists.return_value = False

    await WeaviateSchemaService(client).ensure_schema()

    calls = client.collections.create.call_args_list
    assert {call.kwargs["name"] for call in calls} == {
        settings.WEAVIATE_PAGE_COLLECTION_NAME,
        settings.WEAVIATE_CHUNK_COLLECTION_NAME,
    }
    vectors_by_name = {
        call.kwargs["name"]: call.kwargs["vector_config"] for call in calls
    }
    assert len(vectors_by_name[settings.WEAVIATE_PAGE_COLLECTION_NAME]) == 2
    assert len(vectors_by_name[settings.WEAVIATE_CHUNK_COLLECTION_NAME]) == 1
    for vector_configs in vectors_by_name.values():
        for vector_config in vector_configs:
            assert vector_config.vectorizer.model == settings.WEAVIATE_EMBEDDING_MODEL
            assert (
                vector_config.vectorizer.dimensions
                == settings.WEAVIATE_EMBEDDING_DIMENSIONS
            )


async def test_ensure_schema_keeps_compatible_collections(
    schema_dependencies: dict[str, MagicMock],
) -> None:
    client = schema_dependencies["client"]

    await WeaviateSchemaService(client).ensure_schema()

    client.collections.create.assert_not_called()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("vectorizer", "text2vec-cohere"),
        ("model", "text-embedding-3-small"),
        ("dimensions", 3072),
    ],
)
async def test_ensure_schema_rejects_incompatible_vector_config(
    schema_dependencies: dict[str, MagicMock], field: str, value: Any
) -> None:
    config = schema_dependencies["page_collection"].config.get.return_value
    vectorizer = config.vector_config["title_vector"].vectorizer
    if field == "vectorizer":
        vectorizer.vectorizer = value
    else:
        vectorizer.model[field] = value

    with pytest.raises(WeaviateSchemaError, match="reindex_weaviate.py"):
        await WeaviateSchemaService(schema_dependencies["client"]).ensure_schema()


async def test_ensure_schema_rejects_incompatible_named_vectors(
    schema_dependencies: dict[str, MagicMock],
) -> None:
    config = schema_dependencies["page_collection"].config.get.return_value
    del config.vector_config["memo_vector"]

    with pytest.raises(WeaviateSchemaError, match="named vectors"):
        await WeaviateSchemaService(schema_dependencies["client"]).ensure_schema()


def test_validate_rejects_missing_collection(
    schema_dependencies: dict[str, MagicMock],
) -> None:
    client = schema_dependencies["client"]
    client.collections.exists.return_value = False

    with pytest.raises(WeaviateSchemaError, match="collection is missing"):
        WeaviateSchemaService(client).validate()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing", "required property 'pageId' is missing"),
        ("wrong_type", "property 'pageId' type is 'text', expected 'int'"),
    ],
)
def test_validate_rejects_incompatible_property(
    schema_dependencies: dict[str, MagicMock], mutation: str, message: str
) -> None:
    config = schema_dependencies["page_collection"].config.get.return_value
    if mutation == "missing":
        config.properties = [
            prop for prop in config.properties if prop.name != "pageId"
        ]
    else:
        next(
            prop for prop in config.properties if prop.name == "pageId"
        ).data_type = DataType.TEXT

    with pytest.raises(WeaviateSchemaError, match=message):
        WeaviateSchemaService(schema_dependencies["client"]).validate()
