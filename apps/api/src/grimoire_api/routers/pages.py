"""Pages management router."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from ..dependencies import get_file_repository, get_page_service
from ..repositories.file_repository import FileRepository
from ..services.page_service import PageService
from ..utils.exceptions import FileOperationError

router = APIRouter(prefix="/api/v1", tags=["pages"])


@router.get("/pages", response_model=dict)
async def get_pages(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort: str = Query("created_at", regex="^(id|url|title|created_at|updated_at)$"),
    order: str = Query("desc", regex="^(asc|desc)$"),
    status: str = Query("all", regex="^(all|completed|processing|failed)$"),
    page_service: PageService = Depends(get_page_service),
) -> dict:
    """ページ一覧取得.

    Args:
        limit: 取得件数制限
        offset: オフセット
        sort: ソートフィールド
        order: ソート順
        status: ステータスフィルター
        page_service: ページサービス

    Returns:
        ページ一覧とメタデータ
    """
    try:
        pages_data, total = await page_service.list_pages(
            limit=limit,
            offset=offset,
            sort=sort,
            order=order,
            status_filter=status if status != "all" else None,
        )

        return {
            "pages": pages_data,
            "total": total,
            "limit": limit,
            "offset": offset,
            "status_filter": status,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pages/{page_id}")
async def get_page_detail(
    page_id: int,
    page_service: PageService = Depends(get_page_service),
    file_repo: FileRepository = Depends(get_file_repository),
) -> dict:
    """ページ詳細取得.

    Args:
        page_id: ページID
        page_service: ページサービス
        file_repo: ファイルリポジトリ

    Returns:
        ページ詳細

    Raises:
        HTTPException: ページが見つからない場合
    """
    try:
        page_data = await page_service.get_page_detail(page_id)
        if not page_data:
            raise HTTPException(status_code=404, detail="Page not found")

        page_data["has_json_file"] = await file_repo.file_exists(page_id)

        return page_data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pages/{page_id}/json")
async def get_page_json(
    page_id: int,
    file_repo: FileRepository = Depends(get_file_repository),
) -> JSONResponse:
    """ページのJSONファイル取得.

    Args:
        page_id: ページID
        file_repo: ファイルリポジトリ

    Returns:
        JSONファイルの内容

    Raises:
        HTTPException: ファイルが見つからない場合
    """
    try:
        json_data = await file_repo.load_json_file(page_id)
        return JSONResponse(
            content=json_data,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )

    except FileOperationError:
        raise HTTPException(status_code=404, detail="JSON file not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
