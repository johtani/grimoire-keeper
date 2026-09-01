"""Search router."""

from fastapi import APIRouter, Depends

from ..dependencies import get_search_service
from ..models.request import SearchRequest
from ..models.response import COMMON_ERROR_RESPONSES, SearchResponse
from ..services.search_service import SearchService
from ..utils.metrics import search_requests, search_results_count

router = APIRouter(prefix="/api/v1", tags=["search"], responses=COMMON_ERROR_RESPONSES)


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
            filters=(
                request.filters.model_dump(exclude_none=True)
                if request.filters
                else None
            ),
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

    except Exception:
        search_requests.add(1, {"search_type": "vector", "status": "error"})
        raise


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
    results = await search_service.keyword_search(
        keywords=keywords,
        limit=limit,
    )

    return SearchResponse(
        results=results,
        total=len(results),
        query=" ".join(keywords),
    )
