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

    def create_log_sync(self, url: str, status: str, page_id: int | None = None) -> int:
        """ログ作成（同期版）.

        Args:
            url: URL
            status: ステータス
            page_id: ページID

        Returns:
            作成されたログID
        """
        try:
            query = """
            INSERT INTO process_logs (page_id, url, status, created_at)
            VALUES (?, ?, ?, ?)
            """
            cursor = self.db.execute(query, (page_id, url, status, datetime.now()))
            return cursor.lastrowid or 0
        except Exception as e:
            raise DatabaseError(f"Failed to create log: {str(e)}")

    def get_logs_by_status_sync(self, status: str) -> list[ProcessLog]:
        """ステータス別ログ取得（同期版）.

        Args:
            status: ステータス

        Returns:
            ログデータのリスト
        """
        try:
            query = """
            SELECT * FROM process_logs
            WHERE status = ?
            ORDER BY created_at DESC
            """
            results = self.db.fetch_all(query, (status,))
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
        """ステータス更新.

        Args:
            log_id: ログID
            status: ステータス
            error_message: エラーメッセージ
        """
        try:
            query = """
            UPDATE process_logs
            SET status = ?, error_message = ?
            WHERE id = ?
            """
            self.db.execute(query, (status, error_message, log_id))
        except Exception as e:
            raise DatabaseError(f"Failed to update status: {str(e)}")

    async def get_logs_by_status(self, status: str) -> list[ProcessLog]:
        """ステータス別ログ取得.

        Args:
            status: ステータス

        Returns:
            ログデータのリスト
        """
        return self.get_logs_by_status_sync(status)

    async def get_all_logs(self, limit: int = 100, offset: int = 0) -> list[ProcessLog]:
        """全ログ取得.

        Args:
            limit: 取得件数制限
            offset: オフセット

        Returns:
            ログデータのリスト
        """
        try:
            query = """
            SELECT * FROM process_logs
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """
            results = self.db.fetch_all(query, (limit, offset))
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
