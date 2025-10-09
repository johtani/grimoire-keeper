"""Pages management router."""

from fastapi import APIRouter, Depends, HTTPException, Query

from ..models.response import PageResponse
from ..repositories.page_repository import PageRepository

router = APIRouter(prefix="/api/v1", tags=["pages"])


def get_page_repository() -> PageRepository:
    """ページリポジトリ依存性注入."""
    return PageRepository()


@router.get("/pages", response_model=dict)
async def get_pages(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort: str = Query("created_at", regex="^(id|url|title|created_at|updated_at)$"),
    order: str = Query("desc", regex="^(asc|desc)$"),
    status: str = Query("all", regex="^(all|completed|processing|failed)$"),
    page_repo: PageRepository = Depends(get_page_repository),
) -> dict:
    """ページ一覧取得.

    Args:
        limit: 取得件数制限
        offset: オフセット
        sort: ソートフィールド
        order: ソート順
        status: ステータスフィルター
        page_repo: ページリポジトリ

    Returns:
        ページ一覧とメタデータ
    """
    try:
        # ステータスフィルター条件
        status_filter = None if status == "all" else status
        
        # ページ取得
        pages = page_repo.get_pages(
            limit=limit,
            offset=offset,
            sort_by=sort,
            order=order,
            status_filter=status_filter
        )
        
        # 総件数取得
        total = page_repo.count_pages(status_filter=status_filter)
        
        return {
            "pages": [
                import json
                keywords = json.loads(page.keywords) if page.keywords else []
                {
                    "id": page.id,
                    "url": page.url,
                    "title": page.title,
                    "memo": page.memo,
                    "summary": page.summary,
                    "keywords": keywords,
                    "status": page.status,
                    "created_at": page.created_at.isoformat() if page.created_at else None,
                    "updated_at": page.updated_at.isoformat() if page.updated_at else None,
                }

                for page in pages
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
            "status_filter": status,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pages/{page_id}", response_model=PageResponse)
async def get_page_detail(
    page_id: int,
    page_repo: PageRepository = Depends(get_page_repository),
) -> PageResponse:
    """ページ詳細取得.

    Args:
        page_id: ページID
        page_repo: ページリポジトリ

    Returns:
        ページ詳細

    Raises:
        HTTPException: ページが見つからない場合
    """
    try:
        page = page_repo.get_page(page_id)
        if not page:
            raise HTTPException(status_code=404, detail="Page not found")

        import json
        keywords = json.loads(page.keywords) if page.keywords else []
        
        return PageResponse(
            id=page.id,
            url=page.url,
            title=page.title,
            memo=page.memo,
            summary=page.summary,
            keywords=json.dumps(keywords) if keywords else None,
            status=page.status,
            created_at=page.created_at.isoformat() if page.created_at else None,
            updated_at=page.updated_at.isoformat() if page.updated_at else None,
            weaviate_id=page.weaviate_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))