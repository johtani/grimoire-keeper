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
from grimoire_api.repositories.page_repository import PageRepository  # noqa: E402
from grimoire_api.services.chunking_service import ChunkingService  # noqa: E402
from grimoire_api.services.vectorizer import VectorizerService  # noqa: E402


async def reindex(max_pages: int | None, dry_run: bool) -> int:
    """成功済みページを新しいWeaviateコレクションへ再構築する."""
    page_repo = PageRepository(DatabaseConnection(read_only=dry_run))
    total_pages = await page_repo.count_pages(status_filter="completed")
    target_count = min(total_pages, max_pages) if max_pages is not None else total_pages
    pages = await page_repo.get_pages(
        limit=target_count,
        status_filter="completed",
        sort_by="id",
        order="asc",
    )
    print(f"対象ページ: {len(pages)} / 成功済みページ: {total_pages}")
    if dry_run:
        for page in pages:
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
        ChunkingService(),
        client,
    )
    succeeded = 0
    failed = 0
    try:
        await vectorizer.ensure_schema()
        for index, page in enumerate(pages, 1):
            if page.id is None:
                failed += 1
                continue
            print(f"[{index}/{len(pages)}] page_id={page.id} {page.url}")
            try:
                page_uuid = await vectorizer.reindex_content(page.id)
                await page_repo.update_weaviate_id(page.id, page_uuid)
                succeeded += 1
            except Exception as e:
                failed += 1
                print(f"  ERROR: {e}")
    finally:
        client.close()

    print(f"完了: success={succeeded}, failed={failed}, total={len(pages)}")
    return 1 if failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SQLiteと保存済みJSONからWeaviate索引を再構築する"
    )
    parser.add_argument("--max-pages", type=_positive_int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(reindex(args.max_pages, args.dry_run)))


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("1以上の整数を指定してください")
    return parsed


if __name__ == "__main__":
    main()
