"""Retry processing router."""

from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import get_retry_service
from ..models.request import ReprocessRequest, RetryAllRequest
from ..models.response import BatchRetryResponse, RetryResponse
from ..services.retry_service import RetryService
from ..utils.exceptions import DatabaseError, GrimoireAPIError

router = APIRouter(prefix="/api/v1", tags=["retry"])


def _raise_retry_error(error: Exception) -> NoReturn:
    if "UNIQUE constraint failed" in str(error):
        raise HTTPException(
            status_code=409, detail="An active job already exists"
        ) from error
    raise HTTPException(status_code=500, detail=str(error)) from error


@router.post(
    "/retry/{page_id}",
    response_model=RetryResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_page(
    page_id: int,
    retry_service: RetryService = Depends(get_retry_service),
) -> RetryResponse:
    """個別ページ再処理.

    Args:
        page_id: ページID
        retry_service: 再処理サービス

    Returns:
        再処理結果
    """
    try:
        result = await retry_service.retry_single_page(page_id)
        return RetryResponse.model_validate(result)
    except (DatabaseError, GrimoireAPIError) as e:
        _raise_retry_error(e)
    except Exception as e:
        _raise_retry_error(e)


@router.post(
    "/reprocess/{page_id}",
    response_model=RetryResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
)
async def reprocess_page(
    page_id: int,
    request: ReprocessRequest | None = None,
    retry_service: RetryService = Depends(get_retry_service),
) -> RetryResponse:
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
        return RetryResponse.model_validate(result)
    except Exception as e:
        _raise_retry_error(e)


@router.post(
    "/retry-failed",
    response_model=BatchRetryResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_all_failed(
    request: RetryAllRequest | None = None,
    retry_service: RetryService = Depends(get_retry_service),
) -> BatchRetryResponse:
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
        return BatchRetryResponse.model_validate(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
