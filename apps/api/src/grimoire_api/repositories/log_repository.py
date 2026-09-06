"""Log repository."""

from ..utils.datetime import utc_now_isoformat
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
        self,
        url: str,
        status: str,
        page_id: int | None = None,
        *,
        job_id: int | None = None,
        attempt: int | None = None,
        error_message: str | None = None,
    ) -> int:
        """Append an immutable process event."""
        try:
            query = """
            INSERT INTO process_logs
                (page_id, job_id, attempt, url, status, error_message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            lastrowid = await self.db.execute(
                query,
                (
                    page_id,
                    job_id,
                    attempt,
                    url,
                    status,
                    error_message,
                    utc_now_isoformat(),
                ),
            )
            return lastrowid or 0
        except Exception as e:
            raise DatabaseError(f"Failed to create log: {str(e)}")

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
