"""Search service for Weaviate."""

from typing import Any

import weaviate
from weaviate.classes.query import MetadataQuery

from ..config import settings
from ..models.response import SearchResult
from ..utils.exceptions import VectorizerError


class SearchService:
    """検索サービス."""

    def __init__(
        self, weaviate_host: str | None = None, weaviate_port: int | None = None
    ):
        """初期化.

        Args:
            weaviate_host: Weaviateホスト名
            weaviate_port: Weaviateポート番号
        """
        self.weaviate_host = weaviate_host or settings.WEAVIATE_HOST
        self.weaviate_port = weaviate_port or settings.WEAVIATE_PORT

    def _get_client(self) -> weaviate.WeaviateClient:
        """Weaviateクライアント取得."""
        return weaviate.connect_to_local(
            host=self.weaviate_host, 
            port=self.weaviate_port,
            headers={"X-OpenAI-Api-Key": settings.OPENAI_API_KEY}
        )

    async def vector_search(
        self, query: str, limit: int = 5, filters: dict | None = None
    ) -> list[SearchResult]:
        """ベクトル検索.

        Args:
            query: 検索クエリ
            limit: 結果件数制限
            filters: フィルタ条件

        Returns:
            検索結果のリスト

        Raises:
            VectorizerError: 検索エラー
        """
        try:
            with self._get_client() as client:
                collection = client.collections.get("GrimoireChunk")

                # クエリ実行
                response = collection.query.near_text(
                    query=query, limit=limit, return_metadata=MetadataQuery(certainty=True)
                )

                # 結果変換
                return self._convert_search_results_v4(response)

        except Exception as e:
            raise VectorizerError(f"Vector search error: {str(e)}")

    async def keyword_search(
        self, keywords: list[str], limit: int = 5
    ) -> list[SearchResult]:
        """キーワード検索.

        Args:
            keywords: キーワードリスト
            limit: 結果件数制限

        Returns:
            検索結果のリスト

        Raises:
            VectorizerError: 検索エラー
        """
        try:
            from weaviate.classes.query import Filter

            with self._get_client() as client:
                collection = client.collections.get("GrimoireChunk")

                # キーワードフィルタで検索
                response = collection.query.fetch_objects(  # type: ignore[call-overload]
                    where=Filter.by_property("keywords").contains_any(keywords), limit=limit
                )

                return self._convert_search_results_v4(response)

        except Exception as e:
            raise VectorizerError(f"Keyword search error: {str(e)}")

    def _build_where_filter(self, filters: dict) -> dict | None:
        """フィルタ条件構築.

        Args:
            filters: フィルタ条件

        Returns:
            Weaviate用フィルタ条件
        """
        conditions = []

        if "url" in filters:
            conditions.append(
                {
                    "path": ["url"],
                    "operator": "Like",
                    "valueText": f"*{filters['url']}*",
                }
            )

        if "keywords" in filters:
            conditions.append(
                {
                    "path": ["keywords"],
                    "operator": "ContainsAny",
                    "valueTextArray": filters["keywords"],
                }
            )

        if "date_from" in filters:
            conditions.append(
                {
                    "path": ["createdAt"],
                    "operator": "GreaterThanEqual",
                    "valueDate": filters["date_from"],
                }
            )

        if "date_to" in filters:
            conditions.append(
                {
                    "path": ["createdAt"],
                    "operator": "LessThanEqual",
                    "valueDate": filters["date_to"],
                }
            )

        if len(conditions) == 1:
            return conditions[0]
        elif len(conditions) > 1:
            return {"operator": "And", "operands": conditions}
        else:
            return None

    def _convert_search_results_v4(self, response: Any) -> list[SearchResult]:
        """検索結果変換 (Weaviate v4).

        Args:
            response: Weaviate v4検索結果

        Returns:
            SearchResultのリスト
        """
        search_results = []

        for obj in response.objects:
            # スコア取得
            score = 0.0
            if (
                hasattr(obj.metadata, "certainty")
                and obj.metadata.certainty is not None
            ):
                score = obj.metadata.certainty
            elif (
                hasattr(obj.metadata, "distance") and obj.metadata.distance is not None
            ):
                score = 1.0 - obj.metadata.distance

            search_result = SearchResult(
                page_id=obj.properties.get("pageId", 0),
                chunk_id=obj.properties.get("chunkId", 0),
                url=obj.properties.get("url", ""),
                title=obj.properties.get("title", ""),
                memo=obj.properties.get("memo"),
                content=obj.properties.get("content", ""),
                summary=obj.properties.get("summary", ""),
                keywords=obj.properties.get("keywords", []),
                created_at=obj.properties.get("createdAt", ""),
                score=score,
            )
            search_results.append(search_result)

        return search_results