"""Test configuration and fixtures."""

import asyncio
import tempfile
from pathlib import Path

import pytest
from grimoire_api.repositories.database import DatabaseConnection
from grimoire_api.repositories.file_repository import FileRepository
from grimoire_api.repositories.log_repository import LogRepository
from grimoire_api.repositories.page_repository import PageRepository


@pytest.fixture(scope="session")
def event_loop():
    """イベントループフィクスチャ."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
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
def temp_storage():
    """一時ストレージフィクスチャ."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def file_repo(temp_storage):
    """ファイルリポジトリフィクスチャ."""
    return FileRepository(storage_path=temp_storage)


@pytest.fixture
async def page_repo(temp_db, file_repo):
    """ページリポジトリフィクスチャ."""
    return PageRepository(db=temp_db, file_repo=file_repo)


@pytest.fixture
async def log_repo(temp_db):
    """ログリポジトリフィクスチャ."""
    return LogRepository(db=temp_db)
