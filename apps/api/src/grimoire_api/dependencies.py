"""Shared dependency injection functions for FastAPI routers."""

from functools import lru_cache

import weaviate
from fastapi import Depends, HTTPException, Request

from .repositories.database import DatabaseConnection
from .repositories.file_repository import FileRepository
from .repositories.log_repository import LogRepository
from .repositories.page_repository import PageRepository
from .services.chunking_service import ChunkingService
from .services.jina_client import JinaClient
from .services.llm_service import LLMService
from .services.retry_service import RetryService
from .services.search_service import SearchService
from .services.url_processor import UrlProcessorService
from .services.vectorizer import VectorizerService

# ---------------------------------------------------------------------------
# Stateless singletons (lru_cache → one instance per process lifetime)
# ---------------------------------------------------------------------------


@lru_cache
def get_db_connection() -> DatabaseConnection:
    """データベース接続シングルトン."""
    return DatabaseConnection()


@lru_cache
def get_file_repository() -> FileRepository:
    """ファイルリポジトリシングルトン."""
    return FileRepository()


@lru_cache
def get_chunking_service() -> ChunkingService:
    """チャンキングサービスシングルトン."""
    return ChunkingService()


@lru_cache
def get_jina_client() -> JinaClient:
    """Jina クライアントシングルトン."""
    return JinaClient()


# ---------------------------------------------------------------------------
# Composed repositories (depend on lru_cache singletons via Depends)
# ---------------------------------------------------------------------------


def get_page_repository(
    db: DatabaseConnection = Depends(get_db_connection),
    file_repo: FileRepository = Depends(get_file_repository),
) -> PageRepository:
    """ページリポジトリ依存性注入."""
    return PageRepository(db, file_repo)


def get_log_repository(
    db: DatabaseConnection = Depends(get_db_connection),
) -> LogRepository:
    """ログリポジトリ依存性注入."""
    return LogRepository(db)


def get_llm_service(
    file_repo: FileRepository = Depends(get_file_repository),
) -> LLMService:
    """LLM サービス依存性注入."""
    return LLMService(file_repo)


# ---------------------------------------------------------------------------
# Weaviate-dependent services (weaviate_client comes from app.state)
# ---------------------------------------------------------------------------


def get_weaviate_client(request: Request) -> weaviate.WeaviateClient:
    """Weaviate クライアントを app.state から取得.

    Raises:
        HTTPException: Weaviate が未接続の場合 (503)
    """
    client: weaviate.WeaviateClient | None = getattr(
        request.app.state, "weaviate_client", None
    )
    if client is None:
        raise HTTPException(status_code=503, detail="Weaviate is not available")
    return client


def get_vectorizer_service(
    page_repo: PageRepository = Depends(get_page_repository),
    file_repo: FileRepository = Depends(get_file_repository),
    chunking_service: ChunkingService = Depends(get_chunking_service),
    weaviate_client: weaviate.WeaviateClient = Depends(get_weaviate_client),
) -> VectorizerService:
    """ベクトル化サービス依存性注入."""
    return VectorizerService(page_repo, file_repo, chunking_service, weaviate_client)


def get_search_service(
    weaviate_client: weaviate.WeaviateClient = Depends(get_weaviate_client),
) -> SearchService:
    """検索サービス依存性注入."""
    return SearchService(weaviate_client=weaviate_client)


def get_url_processor_service(
    jina_client: JinaClient = Depends(get_jina_client),
    llm_service: LLMService = Depends(get_llm_service),
    vectorizer: VectorizerService = Depends(get_vectorizer_service),
    page_repo: PageRepository = Depends(get_page_repository),
    log_repo: LogRepository = Depends(get_log_repository),
) -> UrlProcessorService:
    """URL 処理サービス依存性注入."""
    return UrlProcessorService(
        jina_client=jina_client,
        llm_service=llm_service,
        vectorizer=vectorizer,
        page_repo=page_repo,
        log_repo=log_repo,
    )


def get_retry_service(
    jina_client: JinaClient = Depends(get_jina_client),
    llm_service: LLMService = Depends(get_llm_service),
    vectorizer: VectorizerService = Depends(get_vectorizer_service),
    page_repo: PageRepository = Depends(get_page_repository),
    log_repo: LogRepository = Depends(get_log_repository),
) -> RetryService:
    """再処理サービス依存性注入."""
    return RetryService(
        jina_client=jina_client,
        llm_service=llm_service,
        vectorizer=vectorizer,
        page_repo=page_repo,
        log_repo=log_repo,
    )
