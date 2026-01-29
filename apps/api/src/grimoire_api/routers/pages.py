"""Pages management router."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from ..repositories.file_repository import FileRepository
from ..repositories.page_repository import PageRepository

router = APIRouter(prefix="/api/v1", tags=["pages"])


def get_page_repository() -> PageRepository:
    """ページリポジトリ依存性注入."""
    return PageRepository()


def get_file_repository() -> FileRepository:
    """ファイルリポジトリ依存性注入."""
    return FileRepository()


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
        # ページ取得
        pages_data, total = await page_repo.list_pages(
            limit=limit,
            offset=offset,
            sort=sort,
            order=order,
        )

        # ステータスフィルタリング
        if status != "all":
            pages_data = [p for p in pages_data if p.get("status") == status]
            total = len(pages_data)

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
    page_repo: PageRepository = Depends(get_page_repository),
    file_repo: FileRepository = Depends(get_file_repository),
) -> dict:
    """ページ詳細取得.

    Args:
        page_id: ページID
        page_repo: ページリポジトリ
        file_repo: ファイルリポジトリ

    Returns:
        ページ詳細

    Raises:
        HTTPException: ページが見つからない場合
    """
    try:
        page_data = await page_repo.get_by_id(page_id)
        if not page_data:
            raise HTTPException(status_code=404, detail="Page not found")

        # JSONファイルの存在チェックを追加
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
        if not await file_repo.file_exists(page_id):
            raise HTTPException(status_code=404, detail="JSON file not found")

        json_data = await file_repo.load_json_file(page_id)
        # ブラウザで見やすくするためのheaderを追加
        return JSONResponse(
            content=json_data,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
