"""Search service for Weaviate."""

import weaviate

from ..config import settings
from ..models.response import SearchResult
from ..utils.exceptions import VectorizerError


class SearchService:
    """検索サービス."""

    def __init__(self, weaviate_url: str = None):
        """初期化.

        Args:
            weaviate_url: Weaviate URL
        """
        self.weaviate_url = weaviate_url or settings.WEAVIATE_URL
        self._client = None

    @property
    def client(self):
        """Weaviateクライアント."""
        if self._client is None:
            self._client = weaviate.Client(self.weaviate_url)
        return self._client

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
            # クエリ構築
            search_query = (
                self.client.query.get(
                    "GrimoireChunk",
                    [
                        "pageId",
                        "chunkId",
                        "url",
                        "title",
                        "memo",
                        "content",
                        "summary",
                        "keywords",
                        "createdAt",
                    ],
                )
                .with_near_text({"concepts": [query]})
                .with_limit(limit)
                .with_additional(["certainty"])
            )

            # フィルタ適用
            if filters:
                where_filter = self._build_where_filter(filters)
                if where_filter:
                    search_query = search_query.with_where(where_filter)

            # 検索実行
            result = search_query.do()

            # 結果変換
            return self._convert_search_results(result)

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
            where_filter = {
                "path": ["keywords"],
                "operator": "ContainsAny",
                "valueTextArray": keywords,
            }

            result = (
                self.client.query.get(
                    "GrimoireChunk",
                    [
                        "pageId",
                        "chunkId",
                        "url",
                        "title",
                        "memo",
                        "content",
                        "summary",
                        "keywords",
                        "createdAt",
                    ],
                )
                .with_where(where_filter)
                .with_limit(limit)
                .do()
            )

            return self._convert_search_results(result)

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

    def _convert_search_results(self, result: dict) -> list[SearchResult]:
        """検索結果変換.

        Args:
            result: Weaviate検索結果

        Returns:
            SearchResultのリスト
        """
        search_results = []

        if "data" in result and "Get" in result["data"]:
            chunks = result["data"]["Get"].get("GrimoireChunk", [])

            for chunk in chunks:
                # スコア取得（certaintyまたはdistance）
                score = 0.0
                if "_additional" in chunk:
                    additional = chunk["_additional"]
                    if "certainty" in additional:
                        score = additional["certainty"]
                    elif "distance" in additional:
                        score = 1.0 - additional["distance"]  # distanceを類似度に変換

                search_result = SearchResult(
                    page_id=chunk.get("pageId", 0),
                    chunk_id=chunk.get("chunkId", 0),
                    url=chunk.get("url", ""),
                    title=chunk.get("title", ""),
                    memo=chunk.get("memo"),
                    content=chunk.get("content", ""),
                    summary=chunk.get("summary", ""),
                    keywords=chunk.get("keywords", []),
                    created_at=chunk.get("createdAt", ""),
                    score=score,
                )
                search_results.append(search_result)

        return search_results
