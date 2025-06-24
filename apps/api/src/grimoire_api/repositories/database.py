"""Database connection management."""

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
        self._enable_wal_mode()

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """クエリ実行.

        Args:
            query: SQLクエリ
            params: パラメータ

        Returns:
            カーソル
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout=30000")
            cursor = conn.execute(query, params)
            conn.commit()
            # lastrowidを保存してからクローズ
            lastrowid = cursor.lastrowid
            conn.close()

            # 新しいカーソルオブジェクトを作成して返す
            class MockCursor:
                def __init__(self, lastrowid: int | None) -> None:
                    self.lastrowid = lastrowid

            return MockCursor(lastrowid)  # type: ignore[return-value]
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
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout=30000")
            cursor = conn.execute(query, params)
            result = cursor.fetchone()
            conn.close()
            return result  # type: ignore[no-any-return]
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
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout=30000")
            cursor = conn.execute(query, params)
            result = cursor.fetchall()
            conn.close()
            return result
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

        conn = sqlite3.connect(self.db_path)
        conn.execute(pages_table)
        conn.execute(process_logs_table)
        conn.commit()
        conn.close()

    def _enable_wal_mode(self) -> None:
        """データベースのWALモードを有効化."""
        try:
            conn = sqlite3.connect(self.db_path)
            # WALモードを有効化
            conn.execute("PRAGMA journal_mode=WAL")
            # 同期モードをNORMALに設定（パフォーマンス向上）
            conn.execute("PRAGMA synchronous=NORMAL")
            # キャッシュサイズを増加
            conn.execute("PRAGMA cache_size=10000")
            # タイムアウトを設定
            conn.execute("PRAGMA busy_timeout=30000")
            conn.commit()
            conn.close()
        except Exception:
            # WALモード設定に失敗しても継続
            pass
