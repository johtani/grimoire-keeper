"""Integration checks for the Weaviate 1.38.8 deployment target."""

import os
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
import weaviate
from grimoire_api.config import settings
from grimoire_api.services.vectorizer import VectorizerService

pytestmark = pytest.mark.skipif(
    os.getenv("WEAVIATE_INTEGRATION") != "1",
    reason="set WEAVIATE_INTEGRATION=1 to run against Weaviate 1.38.8",
)


@contextmanager
def _weaviate_client() -> Iterator[weaviate.WeaviateClient]:
    headers = {"X-OpenAI-Api-Key": "integration-test-key"}
    if os.getenv("WEAVIATE_INTEGRATION_EMBEDDED") == "1":
        with tempfile.TemporaryDirectory() as data_path:
            client = weaviate.connect_to_embedded(
                version="1.38.8",
                persistence_data_path=data_path,
                headers=headers,
                environment_variables={
                    "ENABLE_MODULES": "text2vec-openai",
                    "DEFAULT_VECTORIZER_MODULE": "text2vec-openai",
                },
            )
            try:
                yield client
            finally:
                client.close()
        return

    client = weaviate.connect_to_local(
        host=os.getenv("WEAVIATE_INTEGRATION_HOST", "localhost"),
        port=int(os.getenv("WEAVIATE_INTEGRATION_PORT", "8080")),
        grpc_port=int(os.getenv("WEAVIATE_INTEGRATION_GRPC_PORT", "50051")),
        headers=headers,
    )
    try:
        yield client
    finally:
        client.close()


@pytest.mark.asyncio
async def test_weaviate_1_38_creates_separated_collections() -> None:
    """1.38.8でページ・本文の名前付きベクトルスキーマを作成できる."""
    suffix = uuid.uuid4().hex[:8]
    page_collection = f"GrimoirePage{suffix}"
    chunk_collection = f"GrimoireContentChunk{suffix}"
    with _weaviate_client() as client:
        try:
            assert client.is_ready()
            assert client.get_meta()["version"] == "1.38.8"
            vectorizer = VectorizerService(
                page_repo=MagicMock(),
                file_repo=MagicMock(),
                chunking_service=MagicMock(),
                weaviate_client=client,
            )
            with (
                patch.object(
                    settings, "WEAVIATE_PAGE_COLLECTION_NAME", page_collection
                ),
                patch.object(
                    settings,
                    "WEAVIATE_CHUNK_COLLECTION_NAME",
                    chunk_collection,
                ),
            ):
                await vectorizer.ensure_schema()

            assert client.collections.exists(page_collection)
            assert client.collections.exists(chunk_collection)
        finally:
            if client.collections.exists(page_collection):
                client.collections.delete(page_collection)
            if client.collections.exists(chunk_collection):
                client.collections.delete(chunk_collection)
