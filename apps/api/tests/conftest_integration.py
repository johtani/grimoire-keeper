"""統合テスト用設定とフィクスチャ."""

import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from grimoire_api.main import app
from grimoire_api.utils.database_init import ensure_database_initialized


@pytest_asyncio.fixture
async def integration_db():
    """統合テスト用データベースフィクスチャ."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_file:
        db_path = temp_file.name

    # データベース初期化
    success = await ensure_database_initialized(db_path)
    assert success, "Failed to initialize test database"

    yield db_path

    # クリーンアップ
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def integration_client(integration_db):
    """統合テスト用クライアントフィクスチャ."""
    # テスト用データベースパスを設定
    import os
    os.environ["DATABASE_PATH"] = integration_db
    
    with TestClient(app) as client:
        yield client