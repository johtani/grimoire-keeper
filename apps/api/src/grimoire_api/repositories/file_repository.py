"""File operations repository."""

import json
from pathlib import Path
from typing import Any

from ..config import settings
from ..utils.exceptions import FileOperationError


class FileRepository:
    """ファイル操作リポジトリ."""

    def __init__(self, storage_path: str | None = None):
        """初期化.

        Args:
            storage_path: ファイル保存パス
        """
        self.storage_path = Path(storage_path or settings.JSON_STORAGE_PATH)
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def save_json_file_sync(self, page_id: int, data: dict[str, Any]) -> None:
        """JSONファイル保存（同期版）.

        Args:
            page_id: ページID
            data: 保存するデータ
        """
        try:
            file_path = self.storage_path / f"{page_id}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            raise FileOperationError(f"Failed to save JSON file: {str(e)}")

    async def save_json_file(self, page_id: int, data: dict[str, Any]) -> None:
        """JSONファイル保存.

        Args:
            page_id: ページID
            data: 保存するデータ
        """
        self.save_json_file_sync(page_id, data)

    async def load_json_file(self, page_id: int) -> dict[str, Any]:
        """JSONファイル読み込み.

        Args:
            page_id: ページID

        Returns:
            読み込んだデータ
        """
        try:
            file_path = self.storage_path / f"{page_id}.json"
            if not file_path.exists():
                raise FileOperationError(f"JSON file not found: {file_path}")

            with open(file_path, encoding="utf-8") as f:
                return json.load(f)  # type: ignore[no-any-return]
        except json.JSONDecodeError as e:
            raise FileOperationError(f"Invalid JSON format: {str(e)}")
        except Exception as e:
            raise FileOperationError(f"Failed to load JSON file: {str(e)}")

    async def delete_json_file(self, page_id: int) -> None:
        """JSONファイル削除.

        Args:
            page_id: ページID
        """
        try:
            file_path = self.storage_path / f"{page_id}.json"
            if file_path.exists():
                file_path.unlink()
        except Exception as e:
            raise FileOperationError(f"Failed to delete JSON file: {str(e)}")

    async def file_exists(self, page_id: int) -> bool:
        """ファイル存在確認.

        Args:
            page_id: ページID

        Returns:
            ファイルが存在するかどうか
        """
        file_path = self.storage_path / f"{page_id}.json"
        return file_path.exists()
