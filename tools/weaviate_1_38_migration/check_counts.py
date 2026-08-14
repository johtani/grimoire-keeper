#!/usr/bin/env python3
"""Verify the rebuilt Weaviate collections before API cutover."""

import sys
from pathlib import Path
from typing import Any

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "apps" / "api" / "src"))

import weaviate  # noqa: E402
from grimoire_api.config import settings  # noqa: E402
from grimoire_api.repositories.database import DatabaseConnection  # noqa: E402
from grimoire_api.repositories.page_repository import PageRepository  # noqa: E402


def _collection_count(client: Any, collection_name: str) -> int:
    collection = client.collections.get(collection_name)
    result = collection.aggregate.over_all(total_count=True)
    return int(result.total_count or 0)


async def verify_migration() -> int:
    """Compare rebuilt collection counts with successful SQLite pages."""
    expected_pages = await PageRepository(
        DatabaseConnection(read_only=True)
    ).count_pages(status_filter="completed")
    client = weaviate.connect_to_local(
        host=settings.WEAVIATE_HOST,
        port=settings.WEAVIATE_PORT,
        headers={"X-OpenAI-Api-Key": settings.OPENAI_API_KEY},
    )
    try:
        if not client.is_ready():
            print("ERROR: Weaviate is not ready")
            return 1

        required_collections = (
            settings.WEAVIATE_PAGE_COLLECTION_NAME,
            settings.WEAVIATE_CHUNK_COLLECTION_NAME,
        )
        missing = [
            name for name in required_collections if not client.collections.exists(name)
        ]
        if missing:
            print(f"ERROR: missing collections: {', '.join(missing)}")
            return 1

        page_count = _collection_count(client, settings.WEAVIATE_PAGE_COLLECTION_NAME)
        chunk_count = _collection_count(client, settings.WEAVIATE_CHUNK_COLLECTION_NAME)
        print(
            "Migration counts: "
            f"sqlite_pages={expected_pages}, "
            f"weaviate_pages={page_count}, "
            f"weaviate_chunks={chunk_count}"
        )

        if page_count != expected_pages:
            print("ERROR: SQLite and GrimoirePage counts do not match")
            return 1
        if expected_pages > 0 and chunk_count < page_count:
            print("ERROR: GrimoireContentChunk count is smaller than page count")
            return 1
        print("OK: rebuilt Weaviate collections passed count verification")
        return 0
    finally:
        client.close()


def main() -> None:
    import asyncio

    raise SystemExit(asyncio.run(verify_migration()))


if __name__ == "__main__":
    main()
