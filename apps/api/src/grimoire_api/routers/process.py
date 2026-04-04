"""URL processing router."""

import time
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from ..dependencies import get_url_processor_service
from ..models.request import ProcessUrlRequest
from ..models.response import ProcessUrlResponse
from ..services.url_processor import UrlProcessorService
from ..utils.metrics import url_processing_duration, url_processing_requests

router = APIRouter(prefix="/api/v1", tags=["process"])


@router.post("/process-url", response_model=ProcessUrlResponse)
async def process_url(
    request: ProcessUrlRequest,
    background_tasks: BackgroundTasks,
    processor: UrlProcessorService = Depends(get_url_processor_service),
) -> ProcessUrlResponse:
    """URL処理エンドポイント.

    Args:
        request: URL処理リクエスト
        background_tasks: バックグラウンドタスク
        processor: URL処理サービス

    Returns:
        処理結果

    Raises:
        HTTPException: 処理エラー
    """
    start_time = time.time()

    try:
        result = await processor.prepare_url_processing(str(request.url), request.memo)

        has_memo = bool(request.memo)
        url_processing_requests.add(1, {"has_memo": str(has_memo)})

        if result["status"] == "already_exists":
            url_processing_requests.add(1, {"status": "already_exists"})
            return ProcessUrlResponse(
                status=result["status"],
                page_id=result["page_id"],
                message=result["message"],
            )

        # バックグラウンドタスクに非同期処理を追加
        background_tasks.add_task(
            processor.process_url_background,
            result["page_id"],
            result["log_id"],
            str(request.url),
        )

        url_processing_requests.add(1, {"status": "processing"})
        return ProcessUrlResponse(
            status="processing",
            page_id=result["page_id"],
            message="URL processing started",
        )

    except Exception as e:
        url_processing_requests.add(1, {"status": "error"})
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        duration = time.time() - start_time
        url_processing_duration.record(duration)


@router.get("/process-status/{page_id}")
async def get_process_status(
    page_id: int,
    processor: UrlProcessorService = Depends(get_url_processor_service),
) -> dict[str, Any]:
    """処理状況取得エンドポイント.

    Args:
        page_id: ページID
        processor: URL処理サービス

    Returns:
        処理状況
    """
    try:
        status = await processor.get_processing_status(page_id)
        return status

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
