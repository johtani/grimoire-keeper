"""Test configuration and fixtures."""

import asyncio
import json
import os
import tempfile
from pathlib import Path

# テスト時はOpenTelemetryを無効化 (モジュールインポート前に設定する必要がある)
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

import pytest
import pytest_asyncio
from grimoire_api.repositories.database import DatabaseConnection
from grimoire_api.repositories.file_repository import FileRepository
from grimoire_api.repositories.log_repository import LogRepository
from grimoire_api.repositories.page_repository import PageRepository
from grimoire_api.utils.datetime import utc_now_isoformat


class PageRepositoryFixture(PageRepository):
    """Test-only repository helpers for arranging page records."""

    async def create_page(self, url: str, title: str, memo: str | None = None) -> int:
        now = utc_now_isoformat()
        page_id = await self.db.execute(
            """INSERT INTO pages
            (url, dedupe_key, title, memo, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'queued', ?, ?)""",
            (url, self.dedupe_key(url), title, memo, now, now),
        )
        return page_id or 0

    async def update_summary_keywords(
        self, page_id: int, summary: str, keywords: list[str]
    ) -> None:
        await self.db.execute(
            """UPDATE pages SET summary=?, keywords=?, updated_at=? WHERE id=?""",
            (
                summary,
                json.dumps(keywords, ensure_ascii=False),
                utc_now_isoformat(),
                page_id,
            ),
        )


class ResponsiveEventLoopPolicy(asyncio.DefaultEventLoopPolicy):
    """スレッドからのwakeup欠落時も定期的に処理を再開するテスト用policy."""

    def new_event_loop(self) -> asyncio.AbstractEventLoop:
        loop = super().new_event_loop()

        def heartbeat() -> None:
            if not loop.is_closed():
                loop.call_later(0.001, heartbeat)

        loop.call_soon(heartbeat)
        return loop


asyncio.set_event_loop_policy(ResponsiveEventLoopPolicy())


@pytest_asyncio.fixture
async def temp_db():
    """一時データベースフィクスチャ."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_file:
        db_path = temp_file.name

    db = DatabaseConnection(db_path)
    await db.initialize_tables()

    yield db

    # クリーンアップ
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def temp_storage() -> str:
    """一時ストレージフィクスチャ."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def file_repo(temp_storage: str) -> FileRepository:
    """ファイルリポジトリフィクスチャ."""
    return FileRepository(storage_path=temp_storage)


@pytest_asyncio.fixture
async def page_repo(
    temp_db: DatabaseConnection,
) -> PageRepositoryFixture:
    """ページリポジトリフィクスチャ."""
    return PageRepositoryFixture(db=temp_db)


@pytest_asyncio.fixture
async def log_repo(temp_db: DatabaseConnection) -> LogRepository:
    """ログリポジトリフィクスチャ."""
    return LogRepository(db=temp_db)


@pytest.fixture
def set_page_status():
    """Return a test-only helper for arranging persisted page status."""

    async def set_status(page_repo, page_id, status) -> None:
        await page_repo.db.execute(
            "UPDATE pages SET status=?, updated_at=? WHERE id=?",
            (status.value, utc_now_isoformat(), page_id),
        )

    return set_status


@pytest.fixture
def get_process_logs():
    """Return a test-only helper for reading immutable process events."""

    async def get_logs(log_repo, *, page_id=None, limit=100):
        where = "WHERE page_id = ?" if page_id is not None else ""
        params = (page_id, limit) if page_id is not None else (limit,)
        return await log_repo.db.fetch_all(
            f"SELECT * FROM process_logs {where} ORDER BY created_at DESC LIMIT ?",
            params,
        )

    return get_logs
