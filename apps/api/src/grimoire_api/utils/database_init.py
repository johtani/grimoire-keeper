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

    except Exception:
        logger.exception("Database initialization failed")
        raise
