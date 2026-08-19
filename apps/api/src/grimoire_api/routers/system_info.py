"""Public runtime service and model information."""

import asyncio
import logging
from enum import Enum
from typing import Any

from fastapi import APIRouter, Request

from ..config import settings
from ..models.response import (
    ExternalServiceInfo,
    SystemInfoResponse,
    VectorizerInfo,
    WeaviateCollectionInfo,
    WeaviateSystemInfo,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["system-info"])


def _vectorizer_name(value: Any) -> str:
    """Return a stable public name for a Weaviate vectorizer value."""
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _public_model_config(model: dict[str, Any]) -> dict[str, Any]:
    """Remove connection and credential fields from public model settings."""
    private_fragments = ("url", "endpoint", "key", "secret", "token")
    return {
        key: value
        for key, value in model.items()
        if not any(fragment in key.lower() for fragment in private_fragments)
    }


def _read_collections(client: Any) -> list[WeaviateCollectionInfo]:
    """Read named-vector configuration using the synchronous Weaviate SDK."""
    result = []
    for collection_name in (
        settings.WEAVIATE_PAGE_COLLECTION_NAME,
        settings.WEAVIATE_CHUNK_COLLECTION_NAME,
    ):
        config = client.collections.get(collection_name).config.get()
        if config.vector_config is None:
            raise ValueError(f"Collection {collection_name} has no named vectors")

        vectors = []
        for vector_name, vector_config in config.vector_config.items():
            vectorizer = vector_config.vectorizer
            model = _public_model_config(dict(vectorizer.model))
            vectors.append(
                VectorizerInfo(
                    name=vector_name,
                    vectorizer=_vectorizer_name(vectorizer.vectorizer),
                    model=model,
                    uses_module_default=not model,
                )
            )
        result.append(WeaviateCollectionInfo(name=collection_name, vectors=vectors))
    return result


@router.get("/system-info", response_model=SystemInfoResponse)
async def system_info(request: Request) -> SystemInfoResponse:
    """Return non-secret service, LLM, and live Weaviate schema information."""
    services = [
        ExternalServiceInfo(name="Jina AI Reader", purpose="URL content retrieval"),
        ExternalServiceInfo(
            name="LiteLLM",
            purpose="Summary and keyword generation",
            model=settings.LLM_MODEL,
        ),
        ExternalServiceInfo(name="Weaviate", purpose="Vector storage and search"),
    ]

    manager = getattr(request.app.state, "weaviate_manager", None)
    try:
        client = await manager.get_ready_client() if manager is not None else None
    except Exception:
        logger.exception("Failed to check Weaviate readiness for system information")
        client = None
    if client is None:
        weaviate = WeaviateSystemInfo(
            status="unavailable",
            message="Weaviate is unavailable",
            collections=[],
        )
    else:
        try:
            collections = await asyncio.to_thread(_read_collections, client)
            weaviate = WeaviateSystemInfo(
                status="available",
                message="Live schema loaded",
                collections=collections,
            )
        except Exception:
            logger.exception("Failed to read Weaviate schema for system information")
            weaviate = WeaviateSystemInfo(
                status="unavailable",
                message="Weaviate schema is unavailable",
                collections=[],
            )

    return SystemInfoResponse(services=services, weaviate=weaviate)
