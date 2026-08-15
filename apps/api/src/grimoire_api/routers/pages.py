"""Pages management router."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from ..dependencies import get_file_repository, get_page_service, get_repair_service
from ..models.database import RepairStatus
from ..models.request import UpdatePageUrlRequest
from ..repositories.file_repository import FileRepository
from ..services.page_service import PageService
from ..services.repair_service import RepairService
from ..utils.exceptions import FileOperationError

router = APIRouter(prefix="/api/v1", tags=["pages"])


@router.get("/repairs")
async def list_repairs(
    repair_status: str = Query(
        RepairStatus.PENDING.value,
        alias="status",
        pattern="^(pending|resolved|all)$",
    ),
    repair_service: RepairService = Depends(get_repair_service),
) -> dict:
    status_filter = None if repair_status == "all" else RepairStatus(repair_status)
    cases = await repair_service.list_cases(status_filter)
    return {"repairs": cases, "total": len(cases)}


@router.post("/repairs/import", status_code=status.HTTP_200_OK)
async def import_repairs(
    repair_service: RepairService = Depends(get_repair_service),
) -> dict:
    try:
        return await repair_service.import_report()
    except FileOperationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/repairs/scan")
async def scan_repairs(
    repair_service: RepairService = Depends(get_repair_service),
) -> dict:
    return await repair_service.scan()


@router.get("/pages/{page_id}/repair")
async def get_page_repair(
    page_id: int,
    request: Request,
    repair_service: RepairService = Depends(get_repair_service),
) -> dict:
    try:
        result = await repair_service.get_detail(page_id)
        manager = getattr(request.app.state, "weaviate_manager", None)
        client = await manager.get_ready_client() if manager else None
        registered: bool | None = None
        if client is not None:
            from weaviate.classes.query import Filter

            from ..config import settings

            collection = client.collections.get(settings.WEAVIATE_PAGE_COLLECTION_NAME)
            response = await asyncio.to_thread(
                collection.query.fetch_objects,
                filters=Filter.by_property("pageId").equal(page_id),
                limit=1,
            )
            registered = bool(response.objects)
        result["weaviate_registered"] = registered
        return result
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/pages/{page_id}/url")
async def update_page_url(
    page_id: int,
    body: UpdatePageUrlRequest,
    repair_service: RepairService = Depends(get_repair_service),
) -> dict:
    try:
        return await repair_service.update_url(
            page_id, body.current_url, str(body.new_url)
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (FileExistsError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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
