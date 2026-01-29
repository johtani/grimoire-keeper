#!/usr/bin/env python3
"""Batch retry script for processing pages from specific status."""

import argparse
import asyncio
import sys
from pathlib import Path

from grimoire_api.repositories.database import DatabaseConnection
from grimoire_api.repositories.file_repository import FileRepository
from grimoire_api.repositories.log_repository import LogRepository
from grimoire_api.repositories.page_repository import PageRepository
from grimoire_api.services.chunking_service import ChunkingService
from grimoire_api.services.jina_client import JinaClient
from grimoire_api.services.llm_service import LLMService
from grimoire_api.services.retry_service import RetryService
from grimoire_api.services.vectorizer import VectorizerService

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "apps" / "api" / "src"))


async def batch_retry_from_status(
    from_step: str,
    interval_seconds: float = 1.0,
    max_pages: int | None = None,
    dry_run: bool = False,
) -> None:
    """特定のステータスからバッチリトライ.

    Args:
        from_step: 開始ステップ ("download", "llm", "vectorize")
        interval_seconds: ページ間のインターバル（秒）
        max_pages: 最大処理ページ数
        dry_run: ドライラン（実際の処理は行わない）
    """
    # 依存関係初期化
    db = DatabaseConnection()
    file_repo = FileRepository()
    page_repo = PageRepository(db, file_repo)
    log_repo = LogRepository(db)

    jina_client = JinaClient()
    llm_service = LLMService(file_repo)
    chunking_service = ChunkingService()
    vectorizer = VectorizerService(page_repo, file_repo, chunking_service)

    retry_service = RetryService(
        jina_client=jina_client,
        llm_service=llm_service,
        vectorizer=vectorizer,
        page_repo=page_repo,
        log_repo=log_repo,
    )

    # ステップに対応する成功ステータスを取得
    status_mapping = {
        "download": "downloaded",
        "llm": "llm_processed",
        "vectorize": "vectorized",
    }

    if from_step not in status_mapping:
        keys = list(status_mapping.keys())
        print(f"Error: Invalid from_step '{from_step}'. Must be one of: {keys}")
        return

    target_status = status_mapping[from_step]

    # 対象ページを取得
    pages = page_repo.get_pages_by_status(target_status)

    if not pages:
        print(f"No pages found with status '{target_status}'")
        return

    # 処理対象を制限
    if max_pages:
        pages = pages[:max_pages]

    print(f"Found {len(pages)} pages with status '{target_status}'")
    print(f"Will retry from step: {from_step}")
    print(f"Interval: {interval_seconds} seconds")

    if dry_run:
        print("DRY RUN - No actual processing will be performed")
        for i, page in enumerate(pages, 1):
            print(f"  {i}. Page {page.id}: {page.url}")
        return

    # 確認
    response = input("Continue? (y/N): ")
    if response.lower() != "y":
        print("Cancelled")
        return

    # バッチ処理実行
    success_count = 0
    error_count = 0

    for i, page in enumerate(pages, 1):
        print(f"\n[{i}/{len(pages)}] Processing page {page.id}: {page.url}")

        try:
            if page.id is not None:
                result = await retry_service.reprocess_page(page.id, from_step)
                if result["status"] == "reprocess_started":
                    print(f"  ✓ Started reprocessing from {result['restart_from']}")
                    success_count += 1
                else:
                    print(f"  ⚠ {result['message']}")
            else:
                print("  ✗ Error: Page ID is None")
                error_count += 1

        except Exception as e:
            print(f"  ✗ Error: {str(e)}")
            error_count += 1

        # インターバル
        if i < len(pages) and interval_seconds > 0:
            print(f"  Waiting {interval_seconds} seconds...")
            await asyncio.sleep(interval_seconds)

    print("\nBatch retry completed:")
    print(f"  Success: {success_count}")
    print(f"  Errors: {error_count}")
    print(f"  Total: {len(pages)}")


def main() -> None:
    """メイン関数."""
    parser = argparse.ArgumentParser(
        description="Batch retry processing from specific status",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # LLM処理が完了したページをベクトル化から再実行
  python batch_retry.py --from-step vectorize --interval 2.0

  # ダウンロード完了ページをLLM処理から再実行（最大10ページ）
  python batch_retry.py --from-step llm --max-pages 10 --interval 5.0

  # ドライラン（実際の処理は行わない）
  python batch_retry.py --from-step download --dry-run
        """,
    )

    parser.add_argument(
        "--from-step",
        choices=["download", "llm", "vectorize"],
        required=True,
        help="Starting step for retry (download/llm/vectorize)",
    )

    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Interval between pages in seconds (default: 1.0)",
    )

    parser.add_argument(
        "--max-pages", type=int, help="Maximum number of pages to process"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without actually doing it",
    )

    args = parser.parse_args()

    # 非同期実行
    asyncio.run(
        batch_retry_from_status(
            from_step=args.from_step,
            interval_seconds=args.interval,
            max_pages=args.max_pages,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
