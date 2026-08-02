"""Tests for the Weaviate reindex command."""

import argparse
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.check_weaviate_migration import verify_migration
from scripts.reindex_weaviate import _positive_int, reindex


@pytest.mark.asyncio
async def test_dry_run_targets_all_completed_pages() -> None:
    """上限未指定なら1万件を超えても成功済み全ページを対象にする."""
    page_repo = MagicMock()
    page_repo.count_pages = AsyncMock(return_value=10_001)
    page_repo.get_pages = AsyncMock(return_value=[])

    with patch("scripts.reindex_weaviate.PageRepository", return_value=page_repo):
        result = await reindex(max_pages=None, dry_run=True)

    assert result == 0
    page_repo.get_pages.assert_awaited_once_with(
        limit=10_001,
        status_filter="completed",
        sort_by="id",
        order="asc",
    )


@pytest.mark.asyncio
async def test_dry_run_respects_max_pages() -> None:
    """--max-pages 指定時だけ対象件数を制限する."""
    page_repo = MagicMock()
    page_repo.count_pages = AsyncMock(return_value=100)
    page_repo.get_pages = AsyncMock(return_value=[])

    with patch("scripts.reindex_weaviate.PageRepository", return_value=page_repo):
        result = await reindex(max_pages=5, dry_run=True)

    assert result == 0
    assert page_repo.get_pages.await_args.kwargs["limit"] == 5


def test_positive_int_rejects_zero() -> None:
    """--max-pages は1以上に限定する."""
    with pytest.raises(argparse.ArgumentTypeError):
        _positive_int("0")


@pytest.mark.asyncio
async def test_verify_migration_accepts_matching_counts() -> None:
    """SQLiteページ数と新コレクション件数が整合すれば成功する."""
    page_repo = MagicMock()
    page_repo.count_pages = AsyncMock(return_value=2)
    client = MagicMock()
    client.is_ready.return_value = True
    client.collections.exists.return_value = True
    page_collection = MagicMock()
    page_collection.aggregate.over_all.return_value.total_count = 2
    chunk_collection = MagicMock()
    chunk_collection.aggregate.over_all.return_value.total_count = 5
    client.collections.get.side_effect = [page_collection, chunk_collection]

    with (
        patch(
            "scripts.check_weaviate_migration.PageRepository",
            return_value=page_repo,
        ),
        patch(
            "scripts.check_weaviate_migration.weaviate.connect_to_local",
            return_value=client,
        ),
    ):
        result = await verify_migration()

    assert result == 0
    client.close.assert_called_once()


@pytest.mark.asyncio
async def test_verify_migration_rejects_page_count_mismatch() -> None:
    """SQLiteとページコレクションの件数不一致を失敗にする."""
    page_repo = MagicMock()
    page_repo.count_pages = AsyncMock(return_value=2)
    client = MagicMock()
    client.is_ready.return_value = True
    client.collections.exists.return_value = True
    page_collection = MagicMock()
    page_collection.aggregate.over_all.return_value.total_count = 1
    chunk_collection = MagicMock()
    chunk_collection.aggregate.over_all.return_value.total_count = 3
    client.collections.get.side_effect = [page_collection, chunk_collection]

    with (
        patch(
            "scripts.check_weaviate_migration.PageRepository",
            return_value=page_repo,
        ),
        patch(
            "scripts.check_weaviate_migration.weaviate.connect_to_local",
            return_value=client,
        ),
    ):
        result = await verify_migration()

    assert result == 1
