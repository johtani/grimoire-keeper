"""Log repository."""

from datetime import datetime

from ..models.database import ProcessLog
from ..utils.exceptions import DatabaseError
from .database import DatabaseConnection


class LogRepository:
    """ログリポジトリ."""

    def __init__(self, db: DatabaseConnection):
        """初期化.

        Args:
            db: データベース接続
        """
        self.db = db

    async def create_log(
        self, url: str, status: str, page_id: int | None = None
    ) -> int:
        """ログ作成."""
        try:
            query = """
            INSERT INTO process_logs (page_id, url, status, created_at)
            VALUES (?, ?, ?, ?)
            """
            lastrowid = await self.db.execute(
                query, (page_id, url, status, datetime.now())
            )
            return lastrowid or 0
        except Exception as e:
            raise DatabaseError(f"Failed to create log: {str(e)}")

    async def get_logs_by_status(self, status: str) -> list[ProcessLog]:
        """ステータス別ログ取得."""
        try:
            query = """
            SELECT * FROM process_logs
            WHERE status = ?
            ORDER BY created_at DESC
            """
            results = await self.db.fetch_all(query, (status,))
            return [
                ProcessLog(
                    id=row["id"],
                    page_id=row["page_id"],
                    url=row["url"],
                    status=row["status"],
                    error_message=row["error_message"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                for row in results
            ]
        except Exception as e:
            raise DatabaseError(f"Failed to get logs by status: {str(e)}")

    async def update_status(
        self, log_id: int, status: str, error_message: str | None = None
    ) -> None:
        """ステータス更新."""
        try:
            query = """
            UPDATE process_logs
            SET status = ?, error_message = ?
            WHERE id = ?
            """
            await self.db.execute(query, (status, error_message, log_id))
        except Exception as e:
            raise DatabaseError(f"Failed to update status: {str(e)}")

    async def get_all_logs(self, limit: int = 100, offset: int = 0) -> list[ProcessLog]:
        """全ログ取得."""
        try:
            query = """
            SELECT * FROM process_logs
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """
            results = await self.db.fetch_all(query, (limit, offset))
            return [
                ProcessLog(
                    id=row["id"],
                    page_id=row["page_id"],
                    url=row["url"],
                    status=row["status"],
                    error_message=row["error_message"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                for row in results
            ]
        except Exception as e:
            raise DatabaseError(f"Failed to get all logs: {str(e)}")

    async def get_failed_page_ids(self) -> set[int]:
        """failedステータスのpage_idセットを取得."""
        try:
            rows = await self.db.fetch_all(
                "SELECT DISTINCT page_id FROM process_logs WHERE status = 'failed' AND page_id IS NOT NULL"  # noqa: E501
            )
            return {row["page_id"] for row in rows}
        except Exception as e:
            raise DatabaseError(f"Failed to get failed page ids: {str(e)}")

    async def has_failed_log(self, page_id: int) -> bool:
        """指定ページの失敗ログが存在するか確認."""
        try:
            query = (
                "SELECT 1 FROM process_logs"
                " WHERE page_id = ? AND status = 'failed' LIMIT 1"
            )
            result = await self.db.fetch_one(query, (page_id,))
            return result is not None
        except Exception as e:
            raise DatabaseError(f"Failed to check failed log: {str(e)}")

    async def get_latest_error(self, page_id: int) -> str | None:
        """最新のエラーメッセージを取得."""
        try:
            query = """
            SELECT error_message FROM process_logs
            WHERE page_id = ? AND status = 'failed' AND error_message IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 1
            """
            result = await self.db.fetch_one(query, (page_id,))
            return result["error_message"] if result else None
        except Exception:
            return None
