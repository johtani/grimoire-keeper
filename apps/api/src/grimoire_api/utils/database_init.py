"""データベース初期化ユーティリティ."""

import logging
from pathlib import Path

from ..repositories.database import DatabaseConnection

logger = logging.getLogger(__name__)


async def ensure_database_initialized(db_path: str | None = None) -> bool:
    """データベースが初期化されていることを確認.

    Args:
        db_path: データベースファイルパス

    Returns:
        初期化が成功したかどうか
    """
    try:
        db = DatabaseConnection(db_path)

        # データベースファイルが存在しない場合は新規作成
        if db_path and not Path(db_path).exists():
            logger.info(f"Creating new database: {db_path}")

        await db.initialize_tables()
        logger.info("Database tables initialized successfully")
        return True

    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return False


async def reset_database(db_path: str | None = None) -> bool:
    """データベースをリセット（テスト用）.

    Args:
        db_path: データベースファイルパス

    Returns:
        リセットが成功したかどうか
    """
    try:
        if db_path and Path(db_path).exists():
            Path(db_path).unlink()
            logger.info(f"Database file removed: {db_path}")

        return await ensure_database_initialized(db_path)

    except Exception as e:
        logger.error(f"Database reset failed: {e}")
        return False
