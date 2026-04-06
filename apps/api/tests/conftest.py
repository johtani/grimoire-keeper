"""Test configuration and fixtures."""

import os
import tempfile
import warnings
from pathlib import Path

# テスト時はOpenTelemetryを無効化 (モジュールインポート前に設定する必要がある)
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

import pytest
import pytest_asyncio
from grimoire_api.repositories.database import DatabaseConnection
from grimoire_api.repositories.file_repository import FileRepository
from grimoire_api.repositories.log_repository import LogRepository
from grimoire_api.repositories.page_repository import PageRepository

# テスト用警告フィルタ
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)


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
) -> PageRepository:
    """ページリポジトリフィクスチャ."""
    return PageRepository(db=temp_db)


@pytest_asyncio.fixture
async def log_repo(temp_db: DatabaseConnection) -> LogRepository:
    """ログリポジトリフィクスチャ."""
    return LogRepository(db=temp_db)
