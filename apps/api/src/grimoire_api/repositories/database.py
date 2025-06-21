"""Database connection management."""

from contextlib import asynccontextmanager

import aiosqlite

from ..config import settings
from ..utils.exceptions import DatabaseError


class DatabaseConnection:
    """データベース接続管理クラス."""

    def __init__(self, db_path: str | None = None):
        """初期化.

        Args:
            db_path: データベースファイルパス
        """
        self.db_path = db_path or settings.DATABASE_PATH

    @asynccontextmanager
    async def get_connection(self) -> any:
        """データベース接続を取得."""
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                conn.row_factory = aiosqlite.Row
                yield conn
        except Exception as e:
            raise DatabaseError(f"Database connection error: {str(e)}")

    async def execute(self, query: str, params: tuple = ()) -> aiosqlite.Cursor:
        """クエリ実行.

        Args:
            query: SQLクエリ
            params: パラメータ

        Returns:
            カーソル
        """
        try:
            async with self.get_connection() as conn:
                cursor = await conn.execute(query, params)
                await conn.commit()
                return cursor  # type: ignore[no-any-return]
        except Exception as e:
            raise DatabaseError(f"Query execution error: {str(e)}")

    async def fetch_one(self, query: str, params: tuple = ()) -> aiosqlite.Row | None:
        """単一行取得.

        Args:
            query: SQLクエリ
            params: パラメータ

        Returns:
            取得した行
        """
        try:
            async with self.get_connection() as conn:
                cursor = await conn.execute(query, params)
                return await cursor.fetchone()  # type: ignore[no-any-return]
        except Exception as e:
            raise DatabaseError(f"Fetch one error: {str(e)}")

    async def fetch_all(self, query: str, params: tuple = ()) -> list[aiosqlite.Row]:
        """全行取得.

        Args:
            query: SQLクエリ
            params: パラメータ

        Returns:
            取得した行のリスト
        """
        try:
            async with self.get_connection() as conn:
                cursor = await conn.execute(query, params)
                return await cursor.fetchall()  # type: ignore[no-any-return]
        except Exception as e:
            raise DatabaseError(f"Fetch all error: {str(e)}")

    async def initialize_tables(self) -> None:
        """テーブル初期化."""
        pages_table = """
        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            memo TEXT,
            summary TEXT,
            keywords TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            weaviate_id TEXT
        )
        """

        process_logs_table = """
        CREATE TABLE IF NOT EXISTS process_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id INTEGER,
            url TEXT NOT NULL,
            status TEXT NOT NULL,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (page_id) REFERENCES pages(id)
        )
        """

        await self.execute(pages_table)
        await self.execute(process_logs_table)
