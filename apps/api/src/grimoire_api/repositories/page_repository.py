"""Page repository."""

import json
from datetime import datetime

from ..models.database import Page
from ..utils.exceptions import DatabaseError
from .database import DatabaseConnection
from .file_repository import FileRepository


class PageRepository:
    """ページリポジトリ."""

    def __init__(self, db: DatabaseConnection, file_repo: FileRepository):
        """初期化.

        Args:
            db: データベース接続
            file_repo: ファイルリポジトリ
        """
        self.db = db
        self.file_repo = file_repo

    def get_page_by_url_sync(self, url: str) -> Page | None:
        """URLでページ取得（同期版）.

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

    def create_page_sync(self, url: str, title: str, memo: str | None = None) -> int:
        """Page作成（同期版）.

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

    def get_page_sync(self, page_id: int) -> Page | None:
        """ページ取得（同期版）.

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

    async def update_summary_keywords(
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

    async def update_page_title(self, page_id: int, title: str) -> None:
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

    async def update_weaviate_id(self, page_id: int, weaviate_id: str) -> None:
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

    async def save_json_file(self, page_id: int, data: dict) -> None:
        """JSONファイル保存.

        Args:
            page_id: ページID
            data: 保存するデータ
        """
        await self.file_repo.save_json_file(page_id, data)

    async def get_all_pages(self, limit: int = 100, offset: int = 0) -> list[Page]:
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