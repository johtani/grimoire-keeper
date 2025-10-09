"""Page repository."""

import json
from datetime import datetime

from ..models.database import Page
from ..utils.exceptions import DatabaseError
from .database import DatabaseConnection
from .file_repository import FileRepository


class PageRepository:
    """ページリポジトリ."""

    def __init__(
        self,
        db: DatabaseConnection | None = None,
        file_repo: FileRepository | None = None,
    ):
        """初期化.

        Args:
            db: データベース接続
            file_repo: ファイルリポジトリ
        """
        self.db = db or DatabaseConnection()
        self.file_repo = file_repo or FileRepository()

    def get_page_by_url(self, url: str) -> Page | None:
        """URLでページ取得.

        Args:
            url: URL

        Returns:
            ページデータ
        """
        try:
            query = "SELECT * FROM pages WHERE url = ?"
            result = self.db.fetch_one(query, (url,))
            if result:
                return Page(
                    id=result["id"],
                    url=result["url"],
                    title=result["title"],
                    memo=result["memo"],
                    summary=result["summary"],
                    keywords=result["keywords"],
                    created_at=datetime.fromisoformat(result["created_at"]),
                    updated_at=datetime.fromisoformat(result["updated_at"]),
                    weaviate_id=result["weaviate_id"],
                )
            return None
        except Exception as e:
            raise DatabaseError(f"Failed to get page by URL: {str(e)}")

    def create_page(self, url: str, title: str, memo: str | None = None) -> int:
        """Page作成.

        Args:
            url: URL
            title: タイトル
            memo: メモ

        Returns:
            作成されたページID
        """
        try:
            query = """
            INSERT INTO pages (url, title, memo, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """
            now = datetime.now()
            cursor = self.db.execute(query, (url, title, memo, now, now))
            return cursor.lastrowid or 0
        except Exception as e:
            raise DatabaseError(f"Failed to create page: {str(e)}")

    def get_page(self, page_id: int) -> Page | None:
        """ページ取得.

        Args:
            page_id: ページID

        Returns:
            ページデータ
        """
        try:
            query = "SELECT * FROM pages WHERE id = ?"
            result = self.db.fetch_one(query, (page_id,))
            if result:
                return Page(
                    id=result["id"],
                    url=result["url"],
                    title=result["title"],
                    memo=result["memo"],
                    summary=result["summary"],
                    keywords=result["keywords"],
                    created_at=datetime.fromisoformat(result["created_at"]),
                    updated_at=datetime.fromisoformat(result["updated_at"]),
                    weaviate_id=result["weaviate_id"],
                )
            return None
        except Exception as e:
            raise DatabaseError(f"Failed to get page: {str(e)}")

    def update_summary_keywords(
        self, page_id: int, summary: str, keywords: list[str]
    ) -> None:
        """要約・キーワード更新.

        Args:
            page_id: ページID
            summary: 要約
            keywords: キーワードリスト
        """
        try:
            query = """
            UPDATE pages
            SET summary = ?, keywords = ?, updated_at = ?
            WHERE id = ?
            """
            self.db.execute(
                query,
                (
                    summary,
                    json.dumps(keywords, ensure_ascii=False),
                    datetime.now(),
                    page_id,
                ),
            )
        except Exception as e:
            raise DatabaseError(f"Failed to update summary/keywords: {str(e)}")

    def update_page_title(self, page_id: int, title: str) -> None:
        """ページタイトル更新.

        Args:
            page_id: ページID
            title: タイトル
        """
        try:
            query = "UPDATE pages SET title = ?, updated_at = ? WHERE id = ?"
            self.db.execute(query, (title, datetime.now(), page_id))
        except Exception as e:
            raise DatabaseError(f"Failed to update page title: {str(e)}")

    def update_weaviate_id(self, page_id: int, weaviate_id: str) -> None:
        """Weaviate ID更新.

        Args:
            page_id: ページID
            weaviate_id: Weaviate ID
        """
        try:
            query = "UPDATE pages SET weaviate_id = ? WHERE id = ?"
            self.db.execute(query, (weaviate_id, page_id))
        except Exception as e:
            raise DatabaseError(f"Failed to update weaviate_id: {str(e)}")

    def save_json_file(self, page_id: int, data: dict) -> None:
        """JSONファイル保存.

        Args:
            page_id: ページID
            data: 保存するデータ
        """
        self.file_repo.save_json_file_sync(page_id, data)

    def get_all_pages(self, limit: int = 100, offset: int = 0) -> list[Page]:
        """全ページ取得.

        Args:
            limit: 取得件数制限
            offset: オフセット

        Returns:
            ページデータのリスト
        """
        try:
            query = """
            SELECT * FROM pages
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """
            results = self.db.fetch_all(query, (limit, offset))
            return [
                Page(
                    id=row["id"],
                    url=row["url"],
                    title=row["title"],
                    memo=row["memo"],
                    summary=row["summary"],
                    keywords=row["keywords"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                    weaviate_id=row["weaviate_id"],
                )
                for row in results
            ]
        except Exception as e:
            raise DatabaseError(f"Failed to get all pages: {str(e)}")

    async def get_by_id(self, page_id: int) -> dict | None:
        """ページIDで取得 (async).

        Args:
            page_id: ページID

        Returns:
            ページデータ
        """
        page = self.get_page(page_id)
        if not page:
            return None

        # エラー情報を取得
        error_message = self._get_latest_error(page_id)

        return {
            "id": page.id,
            "url": page.url,
            "title": page.title,
            "memo": page.memo,
            "summary": page.summary,
            "keywords": json.loads(page.keywords) if page.keywords else [],
            "created_at": page.created_at,
            "updated_at": page.updated_at,
            "weaviate_id": page.weaviate_id,
            "error_message": error_message,
        }

    def _get_latest_error(self, page_id: int) -> str | None:
        """最新のエラーメッセージを取得.

        Args:
            page_id: ページID

        Returns:
            エラーメッセージ
        """
        try:
            query = """
            SELECT error_message FROM process_logs
            WHERE page_id = ? AND status = 'failed' AND error_message IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 1
            """
            result = self.db.fetch_one(query, (page_id,))
            return result["error_message"] if result else None
        except Exception:
            return None

    def get_pages(
        self,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "created_at",
        order: str = "desc",
        status_filter: str | None = None,
    ) -> list[Page]:
        """ページ一覧取得.

        Args:
            limit: 取得件数
            offset: オフセット
            sort_by: ソートフィールド
            order: ソート順序
            status_filter: ステータスフィルター

        Returns:
            ページリスト
        """
        try:
            where_clause = ""
            params = []

            if status_filter:
                if status_filter == "completed":
                    where_clause = (
                        "WHERE summary IS NOT NULL AND weaviate_id IS NOT NULL"
                    )
                elif status_filter == "processing":
                    where_clause = """
                    WHERE (summary IS NULL OR weaviate_id IS NULL)
                    AND id NOT IN (
                        SELECT DISTINCT page_id FROM process_logs
                        WHERE status = 'failed' AND page_id IS NOT NULL
                    )
                    """
                elif status_filter == "failed":
                    where_clause = """
                    WHERE id IN (
                        SELECT DISTINCT page_id FROM process_logs
                        WHERE status = 'failed' AND page_id IS NOT NULL
                    )
                    """

            order_clause = f"ORDER BY {sort_by} {order.upper()}"
            query = f"""
            SELECT * FROM pages
            {where_clause}
            {order_clause}
            LIMIT ? OFFSET ?
            """
            params.extend([limit, offset])

            results = self.db.fetch_all(query, tuple(params))
            return [
                Page(
                    id=row["id"],
                    url=row["url"],
                    title=row["title"],
                    memo=row["memo"],
                    summary=row["summary"],
                    keywords=row["keywords"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                    weaviate_id=row["weaviate_id"],
                )
                for row in results
            ]
        except Exception as e:
            raise DatabaseError(f"Failed to get pages: {str(e)}")

    def count_pages(self, status_filter: str | None = None) -> int:
        """ページ総数取得.

        Args:
            status_filter: ステータスフィルター

        Returns:
            ページ総数
        """
        try:
            where_clause = ""

            if status_filter:
                if status_filter == "completed":
                    where_clause = (
                        "WHERE summary IS NOT NULL AND weaviate_id IS NOT NULL"
                    )
                elif status_filter == "processing":
                    where_clause = """
                    WHERE (summary IS NULL OR weaviate_id IS NULL)
                    AND id NOT IN (
                        SELECT DISTINCT page_id FROM process_logs
                        WHERE status = 'failed' AND page_id IS NOT NULL
                    )
                    """
                elif status_filter == "failed":
                    where_clause = """
                    WHERE id IN (
                        SELECT DISTINCT page_id FROM process_logs
                        WHERE status = 'failed' AND page_id IS NOT NULL
                    )
                    """

            query = f"SELECT COUNT(*) as total FROM pages {where_clause}"
            result = self.db.fetch_one(query)
            return result["total"] if result else 0
        except Exception as e:
            raise DatabaseError(f"Failed to count pages: {str(e)}")

    async def list_pages(
        self,
        limit: int = 20,
        offset: int = 0,
        sort: str = "created_at",
        order: str = "desc",
    ) -> tuple[list[dict], int]:
        """ページ一覧取得 (async).

        Args:
            limit: 取得件数
            offset: オフセット
            sort: ソートフィールド
            order: ソート順序

        Returns:
            ページリストと総数
        """
        try:
            # 総数取得
            count_query = "SELECT COUNT(*) as total FROM pages"
            count_result = self.db.fetch_one(count_query)
            total = count_result["total"] if count_result else 0

            # ページ取得
            order_clause = f"ORDER BY {sort} {order.upper()}"
            query = f"""
            SELECT * FROM pages
            {order_clause}
            LIMIT ? OFFSET ?
            """
            results = self.db.fetch_all(query, (limit, offset))

            pages = []
            for row in results:
                # ステータス判定
                if row["summary"] and row["weaviate_id"]:
                    status = "completed"
                else:
                    # エラーログがあるかチェック
                    error_check = self.db.fetch_one(
                        "SELECT 1 FROM process_logs WHERE page_id = ? AND status = 'failed'",  # noqa: E501
                        (row["id"],),
                    )
                    status = "failed" if error_check else "processing"

                pages.append(
                    {
                        "id": row["id"],
                        "url": row["url"],
                        "title": row["title"],
                        "memo": row["memo"],
                        "summary": row["summary"],
                        "keywords": json.loads(row["keywords"])
                        if row["keywords"]
                        else [],
                        "created_at": datetime.fromisoformat(row["created_at"]),
                        "status": status,
                    }
                )

            return pages, total
        except Exception as e:
            raise DatabaseError(f"Failed to list pages: {str(e)}")
