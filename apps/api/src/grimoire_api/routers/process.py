"""URL processing router."""

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status

from ..dependencies import get_url_processor_service
from ..models.request import ProcessUrlRequest
from ..models.response import ErrorResponse, ProcessStatusResponse, ProcessUrlResponse
from ..services.url_processor import UrlProcessorService
from ..utils.exceptions import ResourceNotFoundError
from ..utils.metrics import (
    url_processing_api_duration,
    url_processing_api_requests,
)

router = APIRouter(prefix="/api/v1", tags=["process"])


@router.post(
    "/process-url",
    response_model=ProcessUrlResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def process_url(
    request: ProcessUrlRequest,
    processor: UrlProcessorService = Depends(get_url_processor_service),
) -> ProcessUrlResponse:
    """URL処理エンドポイント.

    Args:
        request: URL処理リクエスト
        processor: URL処理サービス

    Returns:
        処理結果

    Raises:
        HTTPException: 処理エラー
    """
    start_time = time.perf_counter()
    outcome = "failed"
    has_memo = bool(request.memo)

    try:
        result = await processor.prepare_url_processing(str(request.url), request.memo)

        if result["status"] == "already_exists":
            outcome = "duplicate"
            return ProcessUrlResponse(
                status=result["status"],
                page_id=result["page_id"],
                message=result["message"],
            )

        outcome = "queued"
        return ProcessUrlResponse(
            status="queued",
            page_id=result["page_id"],
            job_id=result["job_id"],
            message="URL processing queued",
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        attributes: dict[str, str | bool] = {
            "outcome": outcome,
            "has_memo": has_memo,
        }
        url_processing_api_requests.add(1, attributes)
        url_processing_api_duration.record(time.perf_counter() - start_time, attributes)


@router.get(
    "/process-status/{page_id}",
    response_model=ProcessStatusResponse,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def get_process_status(
    page_id: Annotated[int, Path(gt=0)],
    processor: UrlProcessorService = Depends(get_url_processor_service),
) -> ProcessStatusResponse:
    """処理状況取得エンドポイント.

    Args:
        page_id: ページID
        processor: URL処理サービス

    Returns:
        処理状況
    """
    try:
        status = await processor.get_processing_status(page_id)
        return ProcessStatusResponse.model_validate(status)

    except ResourceNotFoundError:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
