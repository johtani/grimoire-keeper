"""Pages router for page management endpoints."""

from fastapi import APIRouter, HTTPException, Query

from ..models.response import PageListResponse, PageResponse
from ..repositories.page_repository import PageRepository

router = APIRouter(prefix="/api/v1/pages", tags=["pages"])


@router.get("/{page_id}", response_model=PageResponse)
async def get_page(page_id: int) -> PageResponse:
    """Get detailed information about a specific page."""
    repo = PageRepository()
    page = await repo.get_by_id(page_id)

    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    return PageResponse(**page)


@router.get("", response_model=PageListResponse)
async def list_pages(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort: str = Query("created_at"),
    order: str = Query("desc", regex="^(asc|desc)$"),
) -> PageListResponse:
    """List all processed pages with pagination."""
    repo = PageRepository()
    pages, total = await repo.list_pages(
        limit=limit, offset=offset, sort=sort, order=order
    )

    return PageListResponse(pages=pages, total=total, limit=limit, offset=offset)
