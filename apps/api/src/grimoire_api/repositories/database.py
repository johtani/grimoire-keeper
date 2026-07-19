"""Database connection management."""

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

    async def execute_transaction(self, queries: list[tuple[str, tuple]]) -> None:
        """複数クエリをひとつのトランザクションでアトミックに実行.

        Args:
            queries: (SQLクエリ, パラメータ) のリスト

        Raises:
            DatabaseError: 実行エラー (自動ロールバック)
        """
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute("PRAGMA busy_timeout=30000")
                for query, params in queries:
                    await conn.execute(query, params)
                await conn.commit()
        except Exception as e:
            raise DatabaseError(f"Transaction execution error: {str(e)}")

    async def execute(self, query: str, params: tuple = ()) -> int | None:
        """クエリ実行.

        Args:
            query: SQLクエリ
            params: パラメータ

        Returns:
            lastrowid
        """
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute("PRAGMA busy_timeout=30000")
                cursor = await conn.execute(query, params)
                await conn.commit()
                return cursor.lastrowid
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
            async with aiosqlite.connect(self.db_path) as conn:
                conn.row_factory = aiosqlite.Row
                await conn.execute("PRAGMA busy_timeout=30000")
                async with conn.execute(query, params) as cursor:
                    return await cursor.fetchone()
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
            async with aiosqlite.connect(self.db_path) as conn:
                conn.row_factory = aiosqlite.Row
                await conn.execute("PRAGMA busy_timeout=30000")
                async with conn.execute(query, params) as cursor:
                    return list(await cursor.fetchall())
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
            weaviate_id TEXT,
            last_success_step TEXT DEFAULT NULL,
            status TEXT NOT NULL DEFAULT 'queued'
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

        jobs_table = """
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            current_step TEXT,
            start_step TEXT NOT NULL,
            attempt INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            FOREIGN KEY (page_id) REFERENCES pages(id)
        )
        """

        # 既存テーブルに新しいカラムを追加（マイグレーション）
        migration_query = """
        ALTER TABLE pages ADD COLUMN last_success_step TEXT DEFAULT NULL
        """

        async with aiosqlite.connect(self.db_path) as conn:
            # WALモード・パフォーマンス設定
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA synchronous=NORMAL")
            await conn.execute("PRAGMA cache_size=10000")
            await conn.execute("PRAGMA busy_timeout=30000")

            await conn.execute(pages_table)
            await conn.execute(process_logs_table)
            await conn.execute(jobs_table)

            # マイグレーション実行（カラムが既に存在する場合はエラーを無視）
            try:
                await conn.execute(migration_query)
            except aiosqlite.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    raise

            try:
                await conn.execute(
                    "ALTER TABLE pages ADD COLUMN status TEXT NOT NULL DEFAULT 'queued'"
                )
            except aiosqlite.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    raise

            # jobs がない旧行だけを一度バックフィルする。
            await conn.execute(
                """
                UPDATE pages SET status = CASE
                    WHEN last_success_step = 'completed'
                         OR (summary IS NOT NULL AND weaviate_id IS NOT NULL)
                    THEN 'succeeded' ELSE 'failed' END
                WHERE status = 'queued' AND NOT EXISTS (
                    SELECT 1 FROM jobs WHERE jobs.page_id = pages.id
                )
                """
            )

            # インデックス作成
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_process_logs_page_id"
                " ON process_logs(page_id)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_process_logs_status"
                " ON process_logs(status)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pages_last_success_step"
                " ON pages(last_success_step)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pages_status ON pages(status)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_status_created"
                " ON jobs(status, created_at, id)"
            )
            await conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_active_page"
                " ON jobs(page_id) WHERE status IN ('queued', 'running')"
            )

            await conn.commit()
