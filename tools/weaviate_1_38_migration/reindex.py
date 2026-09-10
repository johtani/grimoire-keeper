#!/usr/bin/env python3
"""Reindex entry point that retains compatibility with the legacy SQLite schema."""

import argparse
import asyncio
from pathlib import Path

from grimoire_api.repositories.database import DatabaseConnection

from scripts.reindex_weaviate import _positive_int, reindex
from tools.weaviate_1_38_migration.page_repository import MigrationPageRepository


def main() -> None:
    parser = argparse.ArgumentParser(
        description="旧SQLiteスキーマ互換でWeaviate索引を再構築する"
    )
    parser.add_argument("--max-pages", type=_positive_int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--repair-pending-output", type=Path)
    args = parser.parse_args()
    page_repo = MigrationPageRepository(DatabaseConnection(read_only=args.dry_run))
    raise SystemExit(
        asyncio.run(
            reindex(
                args.max_pages,
                args.dry_run,
                args.repair_pending_output,
                page_repo,
            )
        )
    )


if __name__ == "__main__":
    main()
