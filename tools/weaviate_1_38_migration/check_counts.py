#!/usr/bin/env python3
"""Verify the rebuilt Weaviate collections before API cutover."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "apps" / "api" / "src"))

import weaviate  # noqa: E402
from grimoire_api.config import settings  # noqa: E402
from grimoire_api.repositories.database import DatabaseConnection  # noqa: E402

from tools.weaviate_1_38_migration.page_repository import (  # noqa: E402
    MigrationPageRepository,
)
from tools.weaviate_1_38_migration.source_validation import (  # noqa: E402
    load_repair_report,
)


def _collection_count(client: Any, collection_name: str) -> int:
    collection = client.collections.get(collection_name)
    result = collection.aggregate.over_all(total_count=True)
    return int(result.total_count or 0)


async def verify_migration(repair_report: Path | None = None) -> int:
    """Compare rebuilt collection counts with successful SQLite pages."""
    expected_pages = await MigrationPageRepository(
        DatabaseConnection(read_only=True)
    ).count_completed_pages()
    expected_migration_pages = expected_pages
    repair_pending_count = 0
    if repair_report is not None:
        try:
            report = load_repair_report(repair_report)
            report_completed = int(report["completed_pages"])
            scanned_pages = int(report["scanned_pages"])
            expected_migration_pages = int(report["migration_targets"])
            repair_pending_count = int(report["repair_pending_count"])
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            print(f"ERROR: invalid repair-pending report: {exc}")
            return 1
        if report_completed != expected_pages or scanned_pages != expected_pages:
            print("ERROR: repair-pending report does not cover all completed pages")
            return 1
        if expected_migration_pages + repair_pending_count != expected_pages:
            print("ERROR: migration target and repair-pending counts do not add up")
            return 1

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
            f"sqlite_completed={expected_pages}, "
            f"migration_targets={expected_migration_pages}, "
            f"repair_pending={repair_pending_count}, "
            f"weaviate_pages={page_count}, "
            f"weaviate_chunks={chunk_count}"
        )

        if page_count != expected_migration_pages:
            print("ERROR: migration targets and GrimoirePage counts do not match")
            return 1
        if expected_migration_pages > 0 and chunk_count < page_count:
            print("ERROR: GrimoireContentChunk count is smaller than page count")
            return 1
        print("OK: rebuilt Weaviate collections passed count verification")
        return 0
    finally:
        client.close()


def main() -> None:
    import asyncio

    parser = argparse.ArgumentParser()
    parser.add_argument("--repair-pending-report", type=Path)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(verify_migration(args.repair_pending_report)))


if __name__ == "__main__":
    main()
