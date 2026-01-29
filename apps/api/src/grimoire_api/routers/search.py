"""Search router."""


from fastapi import APIRouter, Depends, HTTPException

from ..models.request import SearchRequest
from ..models.response import SearchResponse
from ..services.search_service import SearchService
from ..utils.metrics import search_requests, search_results_count

router = APIRouter(prefix="/api/v1", tags=["search"])


def get_search_service() -> SearchService:
    """検索サービス依存性注入."""
    return SearchService()


@router.post("/search", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    search_service: SearchService = Depends(get_search_service),
) -> SearchResponse:
    """ベクトル検索エンドポイント.

    Args:
        request: 検索リクエスト
        search_service: 検索サービス

    Returns:
        検索結果

    Raises:
        HTTPException: 検索エラー
    """
    try:
        results = await search_service.vector_search(
            query=request.query,
            limit=request.limit,
            filters=request.filters,
            vector_name=request.vector_name,
            exclude_keywords=request.exclude_keywords,
        )

        # メトリクス記録
        search_requests.add(
            1,
            {
                "search_type": "vector",
                "query_length": str(len(request.query)),
                "has_filters": str(bool(request.filters)),
            },
        )
        search_results_count.record(len(results), {"search_type": "vector"})

        return SearchResponse(
            results=results,
            total=len(results),
            query=request.query,
        )

    except Exception as e:
        search_requests.add(1, {"search_type": "vector", "status": "error"})
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search/keywords", response_model=SearchResponse)
async def search_by_keywords(
    keywords: list[str],
    limit: int = 5,
    search_service: SearchService = Depends(get_search_service),
) -> SearchResponse:
    """キーワード検索エンドポイント.

    Args:
        keywords: キーワードリスト
        limit: 結果件数制限
        search_service: 検索サービス

    Returns:
        検索結果

    Raises:
        HTTPException: 検索エラー
    """
    try:
        results = await search_service.keyword_search(
            keywords=keywords,
            limit=limit,
        )

        return SearchResponse(
            results=results,
            total=len(results),
            query=" ".join(keywords),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
