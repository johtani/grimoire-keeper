"""統合テスト用設定とフィクスチャ."""

import os
import tempfile
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio

# 統合テスト用警告フィルタ
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)
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
    # テスト用環境変数を設定
    test_env = {
        "DATABASE_PATH": integration_db,
        "JINA_API_KEY": "test-jina-key",
        "GOOGLE_API_KEY": "test-google-key",
        "OPENAI_API_KEY": "test-openai-key",
        "WEAVIATE_HOST": "localhost",
        "WEAVIATE_PORT": "8080",
    }

    with patch.dict(os.environ, test_env):
        with TestClient(app) as client:
            yield client
