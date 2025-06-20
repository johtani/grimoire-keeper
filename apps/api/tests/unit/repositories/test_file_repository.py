"""Test file repository."""

import tempfile
from pathlib import Path

import pytest
from grimoire_api.repositories.file_repository import FileRepository
from grimoire_api.utils.exceptions import FileOperationError


class TestFileRepository:
    """FileRepositoryのテストクラス."""

    @pytest.fixture
    def temp_dir(self):
        """一時ディレクトリフィクスチャ."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def file_repo(self, temp_dir):
        """FileRepositoryフィクスチャ."""
        return FileRepository(storage_path=temp_dir)

    @pytest.mark.asyncio
    async def test_save_and_load_json_file(self, file_repo):
        """JSONファイル保存・読み込みテスト."""
        page_id = 1
        test_data = {
            "data": {
                "title": "Test Title",
                "content": "Test content",
                "url": "https://example.com",
            }
        }

        # 保存
        await file_repo.save_json_file(page_id, test_data)

        # 読み込み
        loaded_data = await file_repo.load_json_file(page_id)
        assert loaded_data == test_data

    @pytest.mark.asyncio
    async def test_file_exists(self, file_repo):
        """ファイル存在確認テスト."""
        page_id = 1
        test_data = {"test": "data"}

        # ファイルが存在しない場合
        assert not await file_repo.file_exists(page_id)

        # ファイル保存後
        await file_repo.save_json_file(page_id, test_data)
        assert await file_repo.file_exists(page_id)

    @pytest.mark.asyncio
    async def test_delete_json_file(self, file_repo):
        """JSONファイル削除テスト."""
        page_id = 1
        test_data = {"test": "data"}

        # ファイル保存
        await file_repo.save_json_file(page_id, test_data)
        assert await file_repo.file_exists(page_id)

        # ファイル削除
        await file_repo.delete_json_file(page_id)
        assert not await file_repo.file_exists(page_id)

    @pytest.mark.asyncio
    async def test_load_nonexistent_file(self, file_repo):
        """存在しないファイルの読み込みテスト."""
        page_id = 999
        with pytest.raises(FileOperationError, match="JSON file not found"):
            await file_repo.load_json_file(page_id)

    @pytest.mark.asyncio
    async def test_save_invalid_json(self, file_repo):
        """不正なJSONデータの保存テスト."""
        page_id = 1
        # 循環参照を含むデータ（JSON化できない）
        invalid_data = {}
        invalid_data["self"] = invalid_data

        with pytest.raises(FileOperationError):
            await file_repo.save_json_file(page_id, invalid_data)

    @pytest.mark.asyncio
    async def test_directory_creation(self, temp_dir):
        """ディレクトリ自動作成テスト."""
        nested_path = Path(temp_dir) / "nested" / "directory"
        FileRepository(storage_path=str(nested_path))

        # ディレクトリが作成されることを確認
        assert nested_path.exists()
        assert nested_path.is_dir()

    @pytest.mark.asyncio
    async def test_unicode_content(self, file_repo):
        """Unicode文字を含むコンテンツのテスト."""
        page_id = 1
        test_data = {
            "title": "日本語タイトル",
            "content": "これは日本語のコンテンツです。🚀",
            "keywords": ["キーワード1", "キーワード2"],
        }

        await file_repo.save_json_file(page_id, test_data)
        loaded_data = await file_repo.load_json_file(page_id)
        assert loaded_data == test_data
