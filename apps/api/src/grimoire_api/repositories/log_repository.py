"""Process log repository."""

from datetime import datetime

from ..models.database import ProcessLog
from ..utils.exceptions import DatabaseError
from .database import DatabaseConnection


class LogRepository:
    """処理ログリポジトリ."""

    def __init__(self, db: DatabaseConnection):
        """初期化.

        Args:
            db: データベース接続
        """
        self.db = db

    async def create_log(self, url: str, status: str, page_id: int = None) -> int:
        """ログ作成.

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
            cursor = await self.db.execute(
                query, (page_id, url, status, datetime.now())
            )
            return cursor.lastrowid
        except Exception as e:
            raise DatabaseError(f"Failed to create log: {str(e)}")

    async def update_status(
        self, log_id: int, status: str, error_message: str = None
    ) -> None:
        """ステータス更新.

        Args:
            log_id: ログID
            status: 新しいステータス
            error_message: エラーメッセージ
        """
        try:
            query = """
            UPDATE process_logs
            SET status = ?, error_message = ?
            WHERE id = ?
            """
            await self.db.execute(query, (status, error_message, log_id))
        except Exception as e:
            raise DatabaseError(f"Failed to update status: {str(e)}")

    async def get_log(self, log_id: int) -> ProcessLog | None:
        """ログ取得.

        Args:
            log_id: ログID

        Returns:
            ログデータ
        """
        try:
            query = "SELECT * FROM process_logs WHERE id = ?"
            result = await self.db.fetch_one(query, (log_id,))
            if result:
                return ProcessLog(
                    id=result["id"],
                    page_id=result["page_id"],
                    url=result["url"],
                    status=result["status"],
                    error_message=result["error_message"],
                    created_at=datetime.fromisoformat(result["created_at"]),
                )
            return None
        except Exception as e:
            raise DatabaseError(f"Failed to get log: {str(e)}")

    async def get_logs_by_status(self, status: str) -> list[ProcessLog]:
        """ステータス別ログ取得.

        Args:
            status: ステータス

        Returns:
            ログデータのリスト
        """
        try:
            query = (
                "SELECT * FROM process_logs WHERE status = ? ORDER BY created_at DESC"
            )
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
