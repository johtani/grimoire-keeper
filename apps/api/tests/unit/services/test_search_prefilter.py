"""SQLite prefiltering and global ranking regression tests."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from grimoire_api.models.database import PageStatus
from grimoire_api.services.search_service import SearchService


def filter_ids(filters):
    clauses = getattr(filters, "filters", [filters])
    assert all(clause.target == "pageId" for clause in clauses)
    return [clause.value for clause in clauses]


@pytest.mark.parametrize("vector", ["title_vector", "memo_vector", "content_vector"])
async def test_match_below_1000_global_candidates(temp_db, page_repo, vector):
    # All 1001 objects exist in the ranking, but only the last matches SQLite.
    async with temp_db.connect() as conn:
        await conn.executemany(
            "INSERT INTO pages (url, title, status, keywords, created_at, updated_at) "
            "VALUES (?, ?, 'succeeded', ?, '2026-01-01', '2026-01-01')",
            [(f"https://example.com/{i}", str(i), '["other"]') for i in range(1000)]
            + [("https://target.example", "target", '["wanted"]')],
        )
        await conn.commit()
    client = MagicMock()
    query = client.collections.get.return_value.query.near_text
    objects = [
        SimpleNamespace(
            properties={"pageId": i, "chunkId": 0},
            metadata=SimpleNamespace(certainty=1 - i / 2000),
        )
        for i in range(1, 1002)
    ]

    def search(**kwargs):
        selected = set(filter_ids(kwargs["filters"]))
        ranked = [obj for obj in objects if obj.properties["pageId"] in selected]
        return SimpleNamespace(
            objects=ranked[kwargs["offset"] : kwargs["offset"] + kwargs["limit"]]
        )

    query.side_effect = search
    results = await SearchService(client, page_repo).vector_search(
        "query",
        filters={
            "keywords": ["wanted"],
            "url": "target",
            "date_from": "2025-01-01",
            "date_to": "2027-01-01",
        },
        vector_name=vector,
        exclude_keywords=["other"],
    )
    assert [result.page_id for result in results] == [1001]
    assert results.truncated is False
    assert filter_ids(query.call_args.kwargs["filters"]) == [1001]


@pytest.mark.parametrize("count", [100, 101, 201])
async def test_id_groups_merge_global_top_results(temp_db, page_repo, count):
    async with temp_db.connect() as conn:
        await conn.executemany(
            "INSERT INTO pages (url, title, status, created_at, updated_at) "
            "VALUES (?, 'title', 'succeeded', '2026-01-01', '2026-01-01')",
            [(f"https://example.com/{i}",) for i in range(count)],
        )
        await conn.commit()
    client = MagicMock()
    query = client.collections.get.return_value.query.near_text

    def search(**kwargs):
        ids = filter_ids(kwargs["filters"])
        return SimpleNamespace(
            objects=[
                SimpleNamespace(
                    properties={"pageId": i, "chunkId": 0},
                    metadata=SimpleNamespace(certainty=i / count),
                )
                for i in sorted(ids, reverse=True)
            ]
        )

    query.side_effect = search
    results = await SearchService(client, page_repo).vector_search("query", limit=2)
    assert [result.page_id for result in results] == [count, count - 1]
    assert query.call_count == (count + 99) // 100
    assert results.truncated is False


@pytest.mark.parametrize("status", list(PageStatus))
async def test_prefilter_and_recheck_share_status_rules(
    page_repo, set_page_status, status
):
    page_id = await page_repo.create_page("https://status.example", "status")
    await set_page_status(page_repo, page_id, status)
    expected = [page_id] if status == PageStatus.SUCCEEDED else []
    assert await page_repo.get_searchable_page_ids() == expected
    assert list(await page_repo.get_searchable_pages_by_ids([page_id])) == expected


async def test_empty_prefilter_skips_weaviate(page_repo):
    client = MagicMock()
    service = SearchService(client, page_repo)
    assert await service.vector_search("query") == []
    assert await service.keyword_search(["keyword"]) == []
    client.collections.get.return_value.query.near_text.assert_not_called()
    client.collections.get.return_value.query.fetch_objects.assert_not_called()


async def test_keyword_search_uses_sqlite_keywords_and_rechecks_deletion(
    page_repo, set_page_status
):
    page_id = await page_repo.create_page("https://keyword.example", "keyword")
    await page_repo.update_summary_keywords(page_id, "summary", ["new-keyword"])
    await set_page_status(page_repo, page_id, PageStatus.SUCCEEDED)
    client = MagicMock()
    query = client.collections.get.return_value.query.fetch_objects
    query.return_value = SimpleNamespace(
        objects=[
            SimpleNamespace(
                properties={"pageId": page_id, "keywords": ["stale-keyword"]},
                metadata=SimpleNamespace(certainty=None, distance=None),
            )
        ]
    )
    service = SearchService(client, page_repo)
    results = await service.keyword_search(["new-keyword"])
    assert [result.page_id for result in results] == [page_id]
    assert filter_ids(query.call_args.kwargs["filters"]) == [page_id]

    original = page_repo.get_searchable_page_ids

    async def changed(*args):
        ids = await original(*args)
        await set_page_status(page_repo, page_id, PageStatus.DELETING)
        return ids

    page_repo.get_searchable_page_ids = changed
    results = await service.keyword_search(["new-keyword"])
    assert results == []
    assert results.truncated is False
