"""Integration tests for RetryService retry flow."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from grimoire_api.models.database import ProcessingStep
from grimoire_api.repositories.database import DatabaseConnection
from grimoire_api.repositories.log_repository import LogRepository
from grimoire_api.repositories.page_repository import PageRepository
from grimoire_api.services.retry_service import RetryService


@pytest.fixture
async def db(tmp_path: object) -> DatabaseConnection:
    """一時ファイルを使った実 DatabaseConnection."""
    db_path = str(tmp_path / "test.db")  # type: ignore[operator]
    conn = DatabaseConnection(db_path=db_path)
    await conn.initialize_tables()
    return conn


@pytest.fixture
def mock_file_repo() -> MagicMock:
    """ファイルシステム書き込みを避けるためのモック FileRepository."""
    repo = MagicMock()
    repo.save_json_file = AsyncMock(return_value=None)
    repo.get_existing_page_ids = MagicMock(return_value=set())
    return repo


@pytest.fixture
async def repos(
    db: DatabaseConnection, mock_file_repo: MagicMock
) -> tuple[PageRepository, LogRepository]:
    """実 PageRepository と LogRepository."""
    page_repo = PageRepository(db=db, file_repo=mock_file_repo)
    log_repo = LogRepository(db=db)
    return page_repo, log_repo


@pytest.fixture
def mock_external_services() -> tuple[AsyncMock, AsyncMock, AsyncMock]:
    """外部サービス (JinaClient / LLMService / VectorizerService) のモック."""
    jina_client = AsyncMock()
    jina_client.fetch_content = AsyncMock(
        return_value={"data": {"title": "Test Title", "content": "Test content"}}
    )

    llm_service = AsyncMock()
    llm_service.generate_summary_keywords = AsyncMock(
        return_value={"summary": "Test summary", "keywords": ["keyword1", "keyword2"]}
    )

    vectorizer = AsyncMock()
    vectorizer.vectorize_content = AsyncMock(return_value=None)

    return jina_client, llm_service, vectorizer


@pytest.fixture
async def retry_service(
    repos: tuple[PageRepository, LogRepository],
    mock_external_services: tuple[AsyncMock, AsyncMock, AsyncMock],
) -> RetryService:
    """RetryService フィクスチャ."""
    page_repo, log_repo = repos
    jina_client, llm_service, vectorizer = mock_external_services
    return RetryService(
        jina_client=jina_client,
        llm_service=llm_service,
        vectorizer=vectorizer,
        page_repo=page_repo,
        log_repo=log_repo,
    )


async def setup_page_with_failed_log(
    page_repo: PageRepository,
    log_repo: LogRepository,
    url: str,
    last_success_step: ProcessingStep | None,
) -> tuple[int, int]:
    """テスト用ページと失敗ログをセットアップするヘルパー."""
    page_id = await page_repo.create_page(url=url, title="Test Page")
    if last_success_step:
        await page_repo.update_success_step(page_id, last_success_step)
    log_id = await log_repo.create_log(url=url, status="failed", page_id=page_id)
    return page_id, log_id


class TestRetryFromDownloadedState:
    """downloaded 状態からのリトライテスト."""

    async def test_llm_and_vectorize_run_but_not_jina(
        self,
        retry_service: RetryService,
        repos: tuple[PageRepository, LogRepository],
        mock_external_services: tuple[AsyncMock, AsyncMock, AsyncMock],
    ) -> None:
        """last_success_step='downloaded' の場合、LLM とベクトル化のみ実行される."""
        page_repo, log_repo = repos
        jina_client, llm_service, vectorizer = mock_external_services

        page_id, _ = await setup_page_with_failed_log(
            page_repo,
            log_repo,
            "https://example.com/downloaded",
            ProcessingStep.DOWNLOADED,
        )

        result = await retry_service.retry_single_page(page_id)

        assert result["status"] == "retry_started"
        assert result["restart_from"] == "llm"

        # Jina は呼ばれない
        jina_client.fetch_content.assert_not_called()
        # LLM とベクトル化は呼ばれる
        llm_service.generate_summary_keywords.assert_called_once_with(page_id)
        vectorizer.vectorize_content.assert_called_once_with(page_id)

        # DB の last_success_step が "completed" になっている
        page = await page_repo.get_page(page_id)
        assert page is not None
        assert page.last_success_step == ProcessingStep.COMPLETED


class TestRetryFromLlmProcessedState:
    """llm_processed 状態からのリトライテスト."""

    async def test_only_vectorize_runs(
        self,
        retry_service: RetryService,
        repos: tuple[PageRepository, LogRepository],
        mock_external_services: tuple[AsyncMock, AsyncMock, AsyncMock],
    ) -> None:
        """last_success_step='llm_processed' の場合、ベクトル化のみ実行される."""
        page_repo, log_repo = repos
        jina_client, llm_service, vectorizer = mock_external_services

        page_id, _ = await setup_page_with_failed_log(
            page_repo,
            log_repo,
            "https://example.com/llm-processed",
            ProcessingStep.LLM_PROCESSED,
        )

        result = await retry_service.retry_single_page(page_id)

        assert result["status"] == "retry_started"
        assert result["restart_from"] == "vectorize"

        # Jina も LLM も呼ばれない
        jina_client.fetch_content.assert_not_called()
        llm_service.generate_summary_keywords.assert_not_called()
        # ベクトル化のみ呼ばれる
        vectorizer.vectorize_content.assert_called_once_with(page_id)

        page = await page_repo.get_page(page_id)
        assert page is not None
        assert page.last_success_step == ProcessingStep.COMPLETED


class TestRetryFromVectorizedState:
    """vectorized 状態からのリトライテスト."""

    async def test_returns_already_completed(
        self,
        retry_service: RetryService,
        repos: tuple[PageRepository, LogRepository],
        mock_external_services: tuple[AsyncMock, AsyncMock, AsyncMock],
    ) -> None:
        """last_success_step='vectorized' の場合、already_completed が返りサービスは呼ばれない."""  # noqa: E501
        page_repo, log_repo = repos
        jina_client, llm_service, vectorizer = mock_external_services

        page_id, _ = await setup_page_with_failed_log(
            page_repo,
            log_repo,
            "https://example.com/vectorized",
            ProcessingStep.VECTORIZED,
        )

        result = await retry_service.retry_single_page(page_id)

        assert result["status"] == "already_completed"
        assert result["page_id"] == page_id

        # どのサービスも呼ばれない
        jina_client.fetch_content.assert_not_called()
        llm_service.generate_summary_keywords.assert_not_called()
        vectorizer.vectorize_content.assert_not_called()


class TestRetryMixedSuccessFailure:
    """一部成功・一部失敗の混在パターンテスト."""

    async def test_continues_after_single_page_failure(
        self,
        repos: tuple[PageRepository, LogRepository],
        mock_external_services: tuple[AsyncMock, AsyncMock, AsyncMock],
    ) -> None:
        """一部ページのリトライが失敗しても残りが処理されること."""
        page_repo, log_repo = repos
        jina_client, llm_service, vectorizer = mock_external_services

        # ページ1: ベクトル化で失敗させる
        page_id1, _ = await setup_page_with_failed_log(
            page_repo,
            log_repo,
            "https://example.com/fail",
            ProcessingStep.LLM_PROCESSED,
        )
        # ページ2: 成功させる
        page_id2, _ = await setup_page_with_failed_log(
            page_repo,
            log_repo,
            "https://example.com/success",
            ProcessingStep.LLM_PROCESSED,
        )

        async def vectorize_side_effect(pid: int) -> None:
            if pid == page_id1:
                raise Exception("vectorize failed")

        vectorizer.vectorize_content = AsyncMock(side_effect=vectorize_side_effect)

        retry_svc = RetryService(
            jina_client=jina_client,
            llm_service=llm_service,
            vectorizer=vectorizer,
            page_repo=page_repo,
            log_repo=log_repo,
        )

        result = await retry_svc.retry_all_failed(delay_seconds=0)

        assert result["status"] == "batch_retry_started"
        assert result["total_failed_pages"] == 2
        assert result["retry_count"] == 1

        # 成功ページは completed になっている
        page2 = await page_repo.get_page(page_id2)
        assert page2 is not None
        assert page2.last_success_step == ProcessingStep.COMPLETED

        # 失敗ページは completed になっていない
        page1 = await page_repo.get_page(page_id1)
        assert page1 is not None
        assert page1.last_success_step != ProcessingStep.COMPLETED


class TestRetryLogGeneration:
    """リトライ中のログ生成確認テスト."""

    async def test_retry_creates_completed_log(
        self,
        retry_service: RetryService,
        repos: tuple[PageRepository, LogRepository],
    ) -> None:
        """リトライ実行後に completed ログが生成されること."""
        page_repo, log_repo = repos

        page_id, _ = await setup_page_with_failed_log(
            page_repo,
            log_repo,
            "https://example.com/log-test",
            ProcessingStep.DOWNLOADED,
        )

        await retry_service.retry_single_page(page_id)

        # 全ログを取得し、このページのログを確認
        all_logs = await log_repo.get_all_logs(limit=50)
        page_logs = [log for log in all_logs if log.page_id == page_id]

        # 失敗ログ (事前挿入) + リトライログ の 2 件が存在する
        assert len(page_logs) == 2

        statuses = {log.status for log in page_logs}
        assert "failed" in statuses  # 元の失敗ログ
        assert "completed" in statuses  # リトライ完了ログ
