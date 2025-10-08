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
            headers={"X-OpenAI-Api-Key": settings.OPENAI_API_KEY},
        )

    async def vector_search(
        self,
        query: str,
        limit: int = 5,
        filters: dict | None = None,
        vector_name: str = "content_vector",
    ) -> list[SearchResult]:
        """ベクトル検索.

        Args:
            query: 検索クエリ
            limit: 結果件数制限
            filters: フィルタ条件
            vector_name: 使用するベクトル名

        Returns:
            検索結果のリスト

        Raises:
            VectorizerError: 検索エラー
        """
        try:
            with self._get_client() as client:
                collection = client.collections.get("GrimoireChunk")

                # フィルター条件構築
                where_filter = self._build_weaviate_filter(filters) if filters else None

                # ベクトル別フィルター追加
                summary_filter = None
                if vector_name != "content_vector":
                    from weaviate.classes.query import Filter
                    summary_filter = Filter.by_property("isSummary").equal(True)

                # フィルター結合
                final_filter = None
                if where_filter and summary_filter:
                    final_filter = Filter.all_of([where_filter, summary_filter])
                elif where_filter:
                    final_filter = where_filter
                elif summary_filter:
                    final_filter = summary_filter

                # クエリ実行
                response = collection.query.near_text(
                    query=query,
                    target_vector=vector_name,
                    limit=limit,
                    filters=final_filter,
                    return_metadata=MetadataQuery(certainty=True),
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
                    filters=Filter.by_property("keywords").contains_any(keywords),
                    limit=limit,
                )

                return self._convert_search_results_v4(response)

        except Exception as e:
            raise VectorizerError(f"Keyword search error: {str(e)}")

    def _build_weaviate_filter(self, filters: dict) -> Any:
        """フィルタ条件構築 (Weaviate v4).

        Args:
            filters: フィルタ条件

        Returns:
            Weaviate v4 Filterオブジェクト
        """
        from weaviate.classes.query import Filter

        conditions = []

        if "url" in filters:
            conditions.append(Filter.by_property("url").like(f"*{filters['url']}*"))

        if "keywords" in filters:
            # keywordsを配列として確実に処理
            keywords_value = filters["keywords"]
            if isinstance(keywords_value, str):
                keywords_value = [keywords_value] if keywords_value.strip() else []
            elif not isinstance(keywords_value, list):
                keywords_value = list(keywords_value) if keywords_value else []

            # 空の配列や空文字列のみの配列を除外
            keywords_value = [k for k in keywords_value if k and k.strip()]

            if keywords_value:  # 有効なキーワードがある場合のみフィルターを追加
                conditions.append(
                    Filter.by_property("keywords").contains_any(keywords_value)
                )

        if "date_from" in filters:
            conditions.append(
                Filter.by_property("createdAt").greater_or_equal(filters["date_from"])
            )

        if "date_to" in filters:
            conditions.append(
                Filter.by_property("createdAt").less_or_equal(filters["date_to"])
            )

        if len(conditions) == 1:
            return conditions[0]
        elif len(conditions) > 1:
            return Filter.all_of(conditions)
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
