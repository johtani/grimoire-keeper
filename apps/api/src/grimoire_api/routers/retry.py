"""Retry processing router."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status

from ..dependencies import get_retry_service
from ..models.request import ReprocessRequest, RetryAllRequest
from ..models.response import BatchRetryResponse, ErrorResponse, RetryResponse
from ..services.retry_service import RetryService
from ..utils.exceptions import ResourceConflictError, ResourceNotFoundError

router = APIRouter(prefix="/api/v1", tags=["retry"])


@router.post(
    "/retry/{page_id}",
    response_model=RetryResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def retry_page(
    page_id: Annotated[int, Path(gt=0)],
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
    except (ResourceNotFoundError, ResourceConflictError):
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post(
    "/reprocess/{page_id}",
    response_model=RetryResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def reprocess_page(
    page_id: Annotated[int, Path(gt=0)],
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
    except (ResourceNotFoundError, ResourceConflictError):
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


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
            )
        else:
            result = await retry_service.retry_all_failed()
        return BatchRetryResponse.model_validate(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
