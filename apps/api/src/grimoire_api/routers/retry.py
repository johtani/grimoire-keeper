"""Retry processing router."""

from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import get_retry_service
from ..models.request import ReprocessRequest, RetryAllRequest
from ..services.retry_service import RetryService

router = APIRouter(prefix="/api/v1", tags=["retry"])


@router.post("/retry/{page_id}", status_code=status.HTTP_202_ACCEPTED)
async def retry_page(
    page_id: int,
    retry_service: RetryService = Depends(get_retry_service),
) -> dict:
    """個別ページ再処理.

    Args:
        page_id: ページID
        retry_service: 再処理サービス

    Returns:
        再処理結果
    """
    try:
        result = await retry_service.retry_single_page(page_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reprocess/{page_id}", status_code=status.HTTP_202_ACCEPTED)
async def reprocess_page(
    page_id: int,
    request: ReprocessRequest | None = None,
    retry_service: RetryService = Depends(get_retry_service),
) -> dict:
    """ページ再処理（成功済みも対象）.

    Args:
        page_id: ページID
        request: 再処理リクエスト
        retry_service: 再処理サービス

    Returns:
        再処理結果
    """
    try:
        from_step = request.from_step if request else "auto"
        result = await retry_service.reprocess_page(page_id, from_step)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/retry-failed", status_code=status.HTTP_202_ACCEPTED)
async def retry_all_failed(
    request: RetryAllRequest | None = None,
    retry_service: RetryService = Depends(get_retry_service),
) -> dict:
    """全失敗ページ再処理.

    Args:
        request: 再処理リクエスト
        retry_service: 再処理サービス

    Returns:
        再処理結果
    """
    try:
        if request:
            result = await retry_service.retry_all_failed(
                max_retries=request.max_retries,
                delay_seconds=request.delay_seconds,
            )
        else:
            result = await retry_service.retry_all_failed()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
