"""Search service for the separated Weaviate page and chunk models."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import weaviate
from weaviate.classes.query import Filter, MetadataQuery

from ..config import settings
from ..models.database import Page
from ..models.response import SearchResult
from ..repositories.page_repository import PageRepository
from ..utils.exceptions import VectorizerError

_PAGE_VECTORS = frozenset({"title_vector", "memo_vector"})
_CONTENT_VECTOR = "content_vector"
_CANDIDATE_BATCH_SIZE = 100
_MAX_CANDIDATES = 1000


class SearchService:
    """ページ代表検索と本文チャンク検索を振り分ける."""

    def __init__(
        self,
        weaviate_client: weaviate.WeaviateClient,
        page_repo: PageRepository | None = None,
    ):
        self.weaviate_client = weaviate_client
        self.page_repo = page_repo or PageRepository()

    async def vector_search(
        self,
        query: str,
        limit: int = 5,
        filters: dict | None = None,
        vector_name: str = _CONTENT_VECTOR,
        exclude_keywords: list[str] | None = None,
    ) -> list[SearchResult]:
        """指定ベクトルに対応するコレクションを検索する."""
        if vector_name not in {*_PAGE_VECTORS, _CONTENT_VECTOR}:
            raise VectorizerError(f"Unsupported vector name: {vector_name}")

        try:
            if vector_name == _CONTENT_VECTOR:
                return await self._content_vector_search(
                    query, limit, filters, exclude_keywords
                )
            return await self._page_vector_search(
                query, limit, filters, vector_name, exclude_keywords
            )
        except VectorizerError:
            raise
        except Exception as e:
            raise VectorizerError(f"Vector search error: {str(e)}")

    async def _content_vector_search(
        self,
        query: str,
        limit: int,
        filters: dict | None,
        exclude_keywords: list[str] | None,
    ) -> list[SearchResult]:
        collection = self.weaviate_client.collections.get(
            settings.WEAVIATE_CHUNK_COLLECTION_NAME
        )

        async def fetch_batch(batch_limit: int, offset: int) -> Any:
            return await asyncio.to_thread(
                collection.query.near_text,
                query=query,
                target_vector=_CONTENT_VECTOR,
                limit=batch_limit,
                offset=offset,
                filters=None,
                return_metadata=MetadataQuery(certainty=True),
            )

        candidates = await self._collect_searchable_candidates(
            fetch_batch, limit, filters, exclude_keywords
        )
        return [
            self._result_from_page(
                page=page,
                score=self._score(obj),
                chunk_id=int(obj.properties.get("chunkId", 0)),
                content=obj.properties.get("content", ""),
            )
            for obj, page in candidates
        ]

    async def _page_vector_search(
        self,
        query: str,
        limit: int,
        filters: dict | None,
        vector_name: str,
        exclude_keywords: list[str] | None,
    ) -> list[SearchResult]:
        collection = self.weaviate_client.collections.get(
            settings.WEAVIATE_PAGE_COLLECTION_NAME
        )

        async def fetch_batch(batch_limit: int, offset: int) -> Any:
            return await asyncio.to_thread(
                collection.query.near_text,
                query=query,
                target_vector=vector_name,
                limit=batch_limit,
                offset=offset,
                filters=None,
                return_metadata=MetadataQuery(certainty=True),
            )

        candidates = await self._collect_searchable_candidates(
            fetch_batch, limit, filters, exclude_keywords
        )
        return [
            self._result_from_page(page, self._score(obj), 0, "")
            for obj, page in candidates
        ]

    async def keyword_search(
        self, keywords: list[str], limit: int = 5
    ) -> list[SearchResult]:
        """ページ代表コレクションをキーワードで検索する."""
        try:
            collection = self.weaviate_client.collections.get(
                settings.WEAVIATE_PAGE_COLLECTION_NAME
            )
            keyword_filter = Filter.by_property("keywords").contains_any(keywords)

            async def fetch_batch(batch_limit: int, offset: int) -> Any:
                return await asyncio.to_thread(
                    collection.query.fetch_objects,
                    filters=keyword_filter,
                    limit=batch_limit,
                    offset=offset,
                )

            candidates = await self._collect_searchable_candidates(
                fetch_batch,
                limit,
                {"keywords": keywords},
                None,
            )
            return [
                self._result_from_page(page, self._score(obj), 0, "")
                for obj, page in candidates
            ]
        except Exception as e:
            raise VectorizerError(f"Keyword search error: {str(e)}")

    async def _collect_searchable_candidates(
        self,
        fetch_batch: Callable[[int, int], Awaitable[Any]],
        limit: int,
        filters: dict | None,
        exclude_keywords: list[str] | None,
    ) -> list[tuple[Any, Page]]:
        """固定サイズで候補を取得し、SQLiteを正として検索可否を判定する."""
        results: list[tuple[Any, Page]] = []
        offset = 0
        while len(results) < limit and offset < _MAX_CANDIDATES:
            batch_limit = min(_CANDIDATE_BATCH_SIZE, _MAX_CANDIDATES - offset)
            response = await fetch_batch(batch_limit, offset)
            objects = response.objects
            if not objects:
                break

            page_ids = list(
                dict.fromkeys(
                    int(obj.properties.get("pageId", 0))
                    for obj in objects
                    if obj.properties.get("pageId")
                )
            )
            pages = await self.page_repo.get_searchable_pages_by_ids(
                page_ids, filters, exclude_keywords
            )
            for obj in objects:
                page = pages.get(int(obj.properties.get("pageId", 0)))
                if page is not None:
                    results.append((obj, page))
                    if len(results) == limit:
                        break

            offset += len(objects)
            if len(objects) < batch_limit:
                break
        return results

    def _build_weaviate_filter(self, filters: dict) -> Any:
        conditions = []
        if filters.get("url"):
            conditions.append(Filter.by_property("url").like(f"*{filters['url']}*"))

        keywords = filters.get("keywords")
        if isinstance(keywords, str):
            keywords = [keywords] if keywords.strip() else []
        elif keywords is not None and not isinstance(keywords, list):
            keywords = list(keywords)
        valid_keywords = [k for k in (keywords or []) if k and k.strip()]
        if valid_keywords:
            conditions.append(
                Filter.by_property("keywords").contains_any(valid_keywords)
            )

        if filters.get("date_from"):
            conditions.append(
                Filter.by_property("createdAt").greater_or_equal(filters["date_from"])
            )
        if filters.get("date_to"):
            conditions.append(
                Filter.by_property("createdAt").less_or_equal(filters["date_to"])
            )
        return self._combine_filters(*conditions)

    @staticmethod
    def _build_exclude_filter(exclude_keywords: list[str]) -> Any:
        valid_keywords = [
            keyword.strip()
            for keyword in exclude_keywords
            if keyword and keyword.strip()
        ]
        if not valid_keywords:
            return None
        return Filter.by_property("keywords").contains_none(valid_keywords)

    @staticmethod
    def _combine_filters(*filters: Any) -> Any:
        present = [condition for condition in filters if condition is not None]
        if not present:
            return None
        if len(present) == 1:
            return present[0]
        return Filter.all_of(present)

    async def _convert_chunk_results(self, response: Any) -> list[SearchResult]:
        page_ids = list(
            {
                int(obj.properties.get("pageId", 0))
                for obj in response.objects
                if obj.properties.get("pageId")
            }
        )
        pages = await self.page_repo.get_pages_by_ids(page_ids)
        results = []
        for obj in response.objects:
            page_id = int(obj.properties.get("pageId", 0))
            page = pages.get(page_id)
            if page is None:
                continue
            results.append(
                self._result_from_page(
                    page=page,
                    score=self._score(obj),
                    chunk_id=int(obj.properties.get("chunkId", 0)),
                    content=obj.properties.get("content", ""),
                )
            )
        return results

    def _convert_page_results(self, response: Any) -> list[SearchResult]:
        return [
            SearchResult(
                page_id=obj.properties.get("pageId", 0),
                chunk_id=0,
                url=obj.properties.get("url", ""),
                title=obj.properties.get("title", ""),
                memo=obj.properties.get("memo") or None,
                content="",
                summary=obj.properties.get("summary", ""),
                keywords=obj.properties.get("keywords", []),
                created_at=obj.properties.get("createdAt", ""),
                score=self._score(obj),
            )
            for obj in response.objects
        ]

    def _convert_search_results_v4(self, response: Any) -> list[SearchResult]:
        """旧内部APIとの互換用にページ代表結果として変換する."""
        return self._convert_page_results(response)

    @staticmethod
    def _result_from_page(
        page: Page, score: float, chunk_id: int, content: str
    ) -> SearchResult:
        if page.id is None:
            raise VectorizerError("Page ID is required")
        return SearchResult(
            page_id=page.id,
            chunk_id=chunk_id,
            url=page.url,
            title=page.title,
            memo=page.memo,
            content=content,
            summary=page.summary or "",
            keywords=page.keywords,
            created_at=page.created_at,
            score=score,
        )

    @staticmethod
    def _score(obj: Any) -> float:
        metadata = obj.metadata
        if getattr(metadata, "certainty", None) is not None:
            return float(metadata.certainty)
        if getattr(metadata, "distance", None) is not None:
            return 1.0 - float(metadata.distance)
        return 0.0
