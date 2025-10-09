"""Retry processing router."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..repositories.file_repository import FileRepository
from ..repositories.log_repository import LogRepository
from ..repositories.page_repository import PageRepository
from ..services.jina_client import JinaClient
from ..services.llm_service import LLMService
from ..services.retry_service import RetryService
from ..services.vectorizer import VectorizerService

router = APIRouter(prefix="/api/v1", tags=["retry"])


class RetryAllRequest(BaseModel):
    """一括再処理リクエスト."""
    max_retries: int | None = None
    delay_seconds: int = 1


def get_retry_service() -> RetryService:
    """再処理サービス依存性注入."""
    page_repo = PageRepository()
    log_repo = LogRepository(page_repo.db)
    file_repo = FileRepository()

    jina_client = JinaClient()
    llm_service = LLMService(file_repo)
    vectorizer = VectorizerService(page_repo, log_repo, file_repo)

    return RetryService(
        jina_client=jina_client,
        llm_service=llm_service,
        vectorizer=vectorizer,
        page_repo=page_repo,
        log_repo=log_repo,
    )


@router.post("/retry/{page_id}")
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


@router.post("/retry-failed")
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
