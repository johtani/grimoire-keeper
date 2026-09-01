"""Database connection management."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

from ..config import settings
from ..utils.exceptions import DatabaseError
from .migrations import migrate_database


class DatabaseConnection:
    """データベース接続管理クラス."""

    def __init__(self, db_path: str | None = None, *, read_only: bool = False):
        """初期化.

        Args:
            db_path: データベースファイルパス
            read_only: SQLiteを読み取り専用モードで開くか
        """
        self.db_path = db_path or settings.DATABASE_PATH
        self.read_only = read_only

    def _connect(self) -> aiosqlite.Connection:
        """設定されたモードでSQLite接続を作成する."""
        if self.read_only:
            database_uri = f"file:{Path(self.db_path).resolve().as_posix()}?mode=ro"
            return aiosqlite.connect(database_uri, uri=True)
        return aiosqlite.connect(self.db_path)

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[aiosqlite.Connection]:
        """外部キー制約を有効化したSQLite接続を提供する."""
        async with self._connect() as conn:
            await conn.execute("PRAGMA foreign_keys=ON")
            await conn.execute("PRAGMA busy_timeout=30000")
            yield conn

    async def execute_transaction(self, queries: list[tuple[str, tuple]]) -> None:
        """複数クエリをひとつのトランザクションでアトミックに実行.

        Args:
            queries: (SQLクエリ, パラメータ) のリスト

        Raises:
            DatabaseError: 実行エラー (自動ロールバック)
        """
        try:
            async with self.connect() as conn:
                for query, params in queries:
                    await conn.execute(query, params)
                await conn.commit()
        except Exception as e:
            raise DatabaseError(f"Transaction execution error: {str(e)}") from e

    async def execute(self, query: str, params: tuple = ()) -> int | None:
        """クエリ実行.

        Args:
            query: SQLクエリ
            params: パラメータ

        Returns:
            lastrowid
        """
        try:
            async with self.connect() as conn:
                cursor = await conn.execute(query, params)
                await conn.commit()
                return cursor.lastrowid
        except Exception as e:
            raise DatabaseError(f"Query execution error: {str(e)}") from e

    async def fetch_one(self, query: str, params: tuple = ()) -> aiosqlite.Row | None:
        """単一行取得.

        Args:
            query: SQLクエリ
            params: パラメータ

        Returns:
            取得した行
        """
        try:
            async with self.connect() as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute(query, params) as cursor:
                    return await cursor.fetchone()
        except Exception as e:
            raise DatabaseError(f"Fetch one error: {str(e)}") from e

    async def fetch_all(self, query: str, params: tuple = ()) -> list[aiosqlite.Row]:
        """全行取得.

        Args:
            query: SQLクエリ
            params: パラメータ

        Returns:
            取得した行のリスト
        """
        try:
            async with self.connect() as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute(query, params) as cursor:
                    return list(await cursor.fetchall())
        except Exception as e:
            raise DatabaseError(f"Fetch all error: {str(e)}") from e

    async def initialize_tables(self) -> None:
        """データベースを最新のスキーマへ移行する."""
        async with self.connect() as conn:
            # WALモード・パフォーマンス設定
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA synchronous=NORMAL")
            await conn.execute("PRAGMA cache_size=10000")

            await migrate_database(conn)
