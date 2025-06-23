"""URL processing router."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from ..models.request import ProcessUrlRequest
from ..models.response import ProcessUrlResponse
from ..repositories.database import DatabaseConnection
from ..repositories.file_repository import FileRepository
from ..repositories.log_repository import LogRepository
from ..repositories.page_repository import PageRepository
from ..services.jina_client import JinaClient
from ..services.llm_service import LLMService
from ..services.url_processor import UrlProcessorService
from ..services.vectorizer import VectorizerService
from ..utils.chunking import TextChunker

router = APIRouter(prefix="/api/v1", tags=["process"])


def get_url_processor() -> UrlProcessorService:
    """URL処理サービス依存性注入."""
    db = DatabaseConnection()
    file_repo = FileRepository()
    page_repo = PageRepository(db, file_repo)
    log_repo = LogRepository(db)

    jina_client = JinaClient()
    llm_service = LLMService(file_repo)
    text_chunker = TextChunker()
    vectorizer = VectorizerService(page_repo, file_repo, text_chunker)

    return UrlProcessorService(
        jina_client=jina_client,
        llm_service=llm_service,
        vectorizer=vectorizer,
        page_repo=page_repo,
        log_repo=log_repo,
    )


@router.post("/process-url", response_model=ProcessUrlResponse)
async def process_url(
    request: ProcessUrlRequest,
    background_tasks: BackgroundTasks,
    processor: UrlProcessorService = Depends(get_url_processor),
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
    try:
        # 同期処理部分を実行
        result = processor.prepare_url_processing(str(request.url), request.memo)
        
        if result["status"] == "already_exists":
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
            str(request.url)
        )
        
        return ProcessUrlResponse(
            status="processing",
            page_id=result["page_id"],
            message="URL processing started",
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/process-status/{page_id}")
def get_process_status(
    page_id: int,
    processor: UrlProcessorService = Depends(get_url_processor),
) -> dict[str, str]:
    """処理状況取得エンドポイント.

    Args:
        page_id: ページID
        processor: URL処理サービス

    Returns:
        処理状況
    """
    try:
        status = processor.get_processing_status(page_id)
        return status

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))