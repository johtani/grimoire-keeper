"""Database connection management."""

import asyncio
import sqlite3

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

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """クエリ実行.

        Args:
            query: SQLクエリ
            params: パラメータ

        Returns:
            カーソル
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(query, params)
                conn.commit()
                return cursor
        except Exception as e:
            raise DatabaseError(f"Query execution error: {str(e)}")

    def fetch_one(self, query: str, params: tuple = ()) -> sqlite3.Row | None:
        """単一行取得.

        Args:
            query: SQLクエリ
            params: パラメータ

        Returns:
            取得した行
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(query, params)
                return cursor.fetchone()
        except Exception as e:
            raise DatabaseError(f"Fetch one error: {str(e)}")

    def fetch_all(self, query: str, params: tuple = ()) -> list[sqlite3.Row]:
        """全行取得.

        Args:
            query: SQLクエリ
            params: パラメータ

        Returns:
            取得した行のリスト
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(query, params)
                return cursor.fetchall()
        except Exception as e:
            raise DatabaseError(f"Fetch all error: {str(e)}")

    def initialize_tables(self) -> None:
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

        self.execute(pages_table)
        self.execute(process_logs_table)