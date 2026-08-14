#!/usr/bin/env python3
"""Rebuild the separated Weaviate indexes from SQLite and saved Jina JSON."""

import argparse
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "apps" / "api" / "src"))

import weaviate  # noqa: E402
from grimoire_api.config import settings  # noqa: E402
from grimoire_api.repositories.database import DatabaseConnection  # noqa: E402
from grimoire_api.repositories.file_repository import FileRepository  # noqa: E402
from grimoire_api.services.chunking_service import ChunkingService  # noqa: E402
from grimoire_api.services.vectorizer import VectorizerService  # noqa: E402

from tools.weaviate_1_38_migration.page_repository import (  # noqa: E402
    MigrationPageRepository,
)
from tools.weaviate_1_38_migration.source_validation import (  # noqa: E402
    classify_stored_source,
    write_repair_report,
)


async def reindex(
    max_pages: int | None, dry_run: bool, repair_pending_output: Path | None = None
) -> int:
    """成功済みページを新しいWeaviateコレクションへ再構築する."""
    page_repo = MigrationPageRepository(DatabaseConnection(read_only=dry_run))
    total_pages = await page_repo.count_completed_pages()
    target_count = min(total_pages, max_pages) if max_pages is not None else total_pages
    pages = await page_repo.get_completed_pages(limit=target_count)
    chunking_service = ChunkingService()
    json_root = Path(settings.JSON_STORAGE_PATH)
    repair_pending = []
    migration_pages = []
    for page in pages:
        pending = classify_stored_source(page, json_root, chunking_service)
        if pending:
            repair_pending.append(pending)
        else:
            migration_pages.append(page)
    if repair_pending_output:
        write_repair_report(
            repair_pending_output,
            completed_pages=total_pages,
            scanned_pages=len(pages),
            migration_targets=len(migration_pages),
            repair_pending=repair_pending,
        )
        print(f"修復待ちレポート: {repair_pending_output}")
    print(
        f"移行対象: {len(migration_pages)}, 修復待ち: {len(repair_pending)}, "
        f"成功済みページ: {total_pages}"
    )
    for pending in repair_pending:
        reason_codes = ", ".join(reason.code for reason in pending.reasons)
        print(f"  REPAIR_PENDING page_id={pending.page_id}: {reason_codes}")
    if dry_run:
        for page in migration_pages:
            print(f"  {page.id}: {page.url}")
        print("ドライランのためWeaviateは変更していません。")
        return 0

    client = weaviate.connect_to_local(
        host=settings.WEAVIATE_HOST,
        port=settings.WEAVIATE_PORT,
        headers={"X-OpenAI-Api-Key": settings.OPENAI_API_KEY},
    )
    vectorizer = VectorizerService(
        page_repo,
        FileRepository(),
        chunking_service,
        client,
    )
    succeeded = 0
    failed = 0
    try:
        await vectorizer.ensure_schema()
        for pending in repair_pending:
            await vectorizer.delete_page_from_index(pending.page_id)
        for index, page in enumerate(migration_pages, 1):
            if page.id is None:
                failed += 1
                continue
            print(f"[{index}/{len(migration_pages)}] page_id={page.id} {page.url}")
            try:
                page_uuid = await vectorizer.reindex_content(page.id)
                await page_repo.update_weaviate_id(page.id, page_uuid)
                succeeded += 1
            except Exception as e:
                failed += 1
                print(f"  ERROR: {e}")
    finally:
        client.close()

    print(
        f"完了: success={succeeded}, failed={failed}, "
        f"repair_pending={len(repair_pending)}, total={len(pages)}"
    )
    return 1 if failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SQLiteと保存済みJSONからWeaviate索引を再構築する"
    )
    parser.add_argument("--max-pages", type=_positive_int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--repair-pending-output", type=Path)
    args = parser.parse_args()
    raise SystemExit(
        asyncio.run(reindex(args.max_pages, args.dry_run, args.repair_pending_output))
    )


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("1以上の整数を指定してください")
    return parsed


if __name__ == "__main__":
    main()
