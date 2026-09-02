"""Pages management router."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import JsonValue

from ..dependencies import (
    get_file_repository,
    get_page_service,
    get_repair_deletion_service,
    get_repair_service,
)
from ..models.database import RepairStatus
from ..models.request import UpdatePageUrlRequest
from ..models.response import (
    COMMON_ERROR_RESPONSES,
    DeletePageResponse,
    ErrorResponse,
    PageListResponse,
    PageResponse,
    RepairDetailResponse,
    RepairImportResponse,
    RepairListResponse,
    RepairScanResponse,
    UpdatePageUrlResponse,
)
from ..repositories.file_repository import FileRepository
from ..services.page_service import PageService
from ..services.repair_service import RepairService
from ..utils.exceptions import (
    FileOperationError,
    RepairDeletionConflictError,
    ResourceConflictError,
    ResourceNotFoundError,
)

router = APIRouter(prefix="/api/v1", tags=["pages"], responses=COMMON_ERROR_RESPONSES)


@router.get("/repairs", response_model=RepairListResponse)
async def list_repairs(
    repair_status: str = Query(
        RepairStatus.PENDING.value,
        alias="status",
        pattern="^(pending|resolved|all)$",
    ),
    repair_service: RepairService = Depends(get_repair_service),
) -> RepairListResponse:
    status_filter = None if repair_status == "all" else RepairStatus(repair_status)
    cases = await repair_service.list_cases(status_filter)
    return RepairListResponse.model_validate({"repairs": cases, "total": len(cases)})


@router.post(
    "/repairs/import",
    response_model=RepairImportResponse,
    status_code=status.HTTP_200_OK,
)
async def import_repairs(
    repair_service: RepairService = Depends(get_repair_service),
) -> RepairImportResponse:
    try:
        result = await repair_service.import_report()
        return RepairImportResponse.model_validate(result)
    except FileOperationError as exc:
        raise ResourceNotFoundError(str(exc)) from exc


@router.post("/repairs/scan", response_model=RepairScanResponse)
async def scan_repairs(
    repair_service: RepairService = Depends(get_repair_service),
) -> RepairScanResponse:
    result = await repair_service.scan()
    return RepairScanResponse.model_validate(result)


@router.get(
    "/pages/{page_id}/repair",
    response_model=RepairDetailResponse,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def get_page_repair(
    page_id: Annotated[int, Path(gt=0)],
    request: Request,
    repair_service: RepairService = Depends(get_repair_service),
) -> RepairDetailResponse:
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
        return RepairDetailResponse.model_validate(result)
    except LookupError as exc:
        raise ResourceNotFoundError(str(exc)) from exc


@router.patch(
    "/pages/{page_id}/url",
    response_model=UpdatePageUrlResponse,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def update_page_url(
    page_id: Annotated[int, Path(gt=0)],
    body: UpdatePageUrlRequest,
    repair_service: RepairService = Depends(get_repair_service),
) -> UpdatePageUrlResponse:
    try:
        result = await repair_service.update_url(
            page_id, body.current_url, str(body.new_url)
        )
        return UpdatePageUrlResponse.model_validate(result)
    except LookupError as exc:
        raise ResourceNotFoundError(str(exc)) from exc
    except (FileExistsError, RuntimeError) as exc:
        raise ResourceConflictError(str(exc)) from exc


@router.delete(
    "/pages/{page_id}",
    response_model=DeletePageResponse,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def delete_page(
    page_id: Annotated[int, Path(gt=0)],
    repair_service: RepairService = Depends(get_repair_deletion_service),
) -> DeletePageResponse:
    """pending repair のページと関連データを削除する."""
    try:
        result = await repair_service.delete_page(page_id)
        return DeletePageResponse.model_validate(result)
    except LookupError as exc:
        raise ResourceNotFoundError(str(exc)) from exc
    except RepairDeletionConflictError as exc:
        raise ResourceConflictError(str(exc)) from exc


@router.get("/pages", response_model=PageListResponse)
async def get_pages(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort: str = Query("created_at", pattern="^(id|url|title|created_at|updated_at)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    status: str = Query("all", pattern="^(all|completed|processing|failed)$"),
    page_service: PageService = Depends(get_page_service),
) -> PageListResponse:
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
    pages_data, total = await page_service.list_pages(
        limit=limit,
        offset=offset,
        sort=sort,
        order=order,
        status_filter=status if status != "all" else None,
    )

    return PageListResponse.model_validate(
        {
            "pages": pages_data,
            "total": total,
            "limit": limit,
            "offset": offset,
            "status_filter": status,
        }
    )


@router.get(
    "/pages/{page_id}",
    response_model=PageResponse,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def get_page_detail(
    page_id: Annotated[int, Path(gt=0)],
    page_service: PageService = Depends(get_page_service),
    file_repo: FileRepository = Depends(get_file_repository),
) -> PageResponse:
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
    page_data = await page_service.get_page_detail(page_id)
    if not page_data:
        raise ResourceNotFoundError(f"Page {page_id} not found")

    page_data["has_json_file"] = await file_repo.file_exists(page_id)
    return PageResponse.model_validate(page_data)


@router.get(
    "/pages/{page_id}/json",
    response_model=JsonValue,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def get_page_json(
    page_id: Annotated[int, Path(gt=0)],
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

    except FileOperationError as exc:
        raise ResourceNotFoundError(f"JSON file for page {page_id} not found") from exc
