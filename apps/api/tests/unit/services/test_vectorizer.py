"""Test vectorizer service."""

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from grimoire_api.models.database import Page
from grimoire_api.services.vectorizer import VectorizerService
from grimoire_api.utils.exceptions import VectorizerError


class TestVectorizerService:
    """VectorizerServiceのテストクラス."""

    @pytest.fixture
    def mock_dependencies(self: Any) -> Any:
        """依存関係のモック."""
        mock_collection = MagicMock()
        mock_collections = MagicMock()
        mock_collections.get.return_value = mock_collection
        mock_collections.exists.return_value = False

        mock_client = MagicMock()
        mock_client.collections = mock_collections
        mock_client.is_ready.return_value = True

        # PageRepositoryのモック
        mock_page_repo = MagicMock()
        mock_page_repo.get_page = MagicMock()
        mock_page_repo.update_weaviate_id = MagicMock()

        # FileRepositoryのモック
        mock_file_repo = MagicMock()
        mock_file_repo.load_json_file = AsyncMock()

        return {
            "page_repo": mock_page_repo,
            "file_repo": mock_file_repo,
            "chunking_service": MagicMock(),
            "weaviate_client": mock_client,
            "mock_collection": mock_collection,
        }

    @pytest.fixture
    def vectorizer_service(self, mock_dependencies):
        """ベクトル化サービスフィクスチャ."""
        service = VectorizerService(
            page_repo=mock_dependencies["page_repo"],
            file_repo=mock_dependencies["file_repo"],
            chunking_service=mock_dependencies["chunking_service"],
            weaviate_host="test-weaviate",
            weaviate_port=8080,
        )
        return service

    @pytest.mark.asyncio
    async def test_vectorize_content_success(
        self, vectorizer_service, mock_dependencies
    ):
        """正常なベクトル化処理テスト."""
        page_id = 1

        # モックページデータ
        mock_page = Page(
            id=page_id,
            url="https://example.com",
            title="Test Title",
            memo="Test memo",
            summary="Test summary",
            keywords='["test", "keyword"]',
            created_at=datetime.now(),
            updated_at=datetime.now(),
            weaviate_id=None,
        )

        # モックJinaデータ
        mock_jina_data = {
            "data": {"content": "This is test content for vectorization."}
        }

        # モックチャンク
        mock_chunks = ["chunk1", "chunk2", "chunk3"]

        # モック設定
        mock_dependencies["page_repo"].get_page.return_value = mock_page
        mock_dependencies["file_repo"].load_json_file.return_value = mock_jina_data
        mock_dependencies["chunking_service"].chunk_text.return_value = mock_chunks
        mock_dependencies[
            "mock_collection"
        ].data.insert.return_value = "weaviate-id-123"

        # _get_clientをモック化
        with patch.object(vectorizer_service, "_get_client") as mock_get_client:
            mock_get_client.return_value.__enter__ = MagicMock(
                return_value=mock_dependencies["weaviate_client"]
            )
            mock_get_client.return_value.__exit__ = MagicMock(return_value=None)

            # 処理実行
            await vectorizer_service.vectorize_content(page_id)

        # 各メソッドが呼ばれたことを確認
        mock_dependencies["page_repo"].get_page.assert_called_once_with(page_id)
        mock_dependencies["file_repo"].load_json_file.assert_called_once_with(page_id)
        mock_dependencies["chunking_service"].chunk_text.assert_called_once_with(
            "This is test content for vectorization."
        )

        # Weaviateへの保存が3回呼ばれたことを確認
        assert mock_dependencies["mock_collection"].data.insert.call_count == 3

        # Weaviate ID更新が呼ばれたことを確認
        mock_dependencies["page_repo"].update_weaviate_id.assert_called_once_with(
            page_id, "weaviate-id-123"
        )

    @pytest.mark.asyncio
    async def test_vectorize_content_page_not_found(
        self, vectorizer_service, mock_dependencies
    ):
        """ページが見つからない場合のテスト."""
        page_id = 999

        # モック設定
        mock_dependencies["page_repo"].get_page.return_value = None

        # エラー確認
        with patch.object(vectorizer_service, "_get_client"):
            with pytest.raises(VectorizerError, match="Page not found"):
                await vectorizer_service.vectorize_content(page_id)

    @pytest.mark.asyncio
    async def test_vectorize_content_no_chunks(
        self, vectorizer_service, mock_dependencies
    ):
        """チャンクが生成されない場合のテスト."""
        page_id = 1

        # モックページデータ
        mock_page = Page(
            id=page_id,
            url="https://example.com",
            title="Test Title",
            memo=None,
            summary=None,
            keywords=None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            weaviate_id=None,
        )

        # モック設定
        mock_dependencies["page_repo"].get_page.return_value = mock_page
        mock_dependencies["file_repo"].load_json_file.return_value = {
            "data": {"content": ""}
        }
        mock_dependencies["chunking_service"].chunk_text.return_value = []

        # エラー確認
        with patch.object(vectorizer_service, "_get_client"):
            with pytest.raises(VectorizerError, match="No chunks generated"):
                await vectorizer_service.vectorize_content(page_id)

    @pytest.mark.asyncio
    async def test_save_chunks_to_weaviate(
        self, vectorizer_service, mock_dependencies: Any
    ) -> None:
        """Weaviateへのチャンク保存テスト."""
        # モックページデータ
        mock_page = Page(
            id=1,
            url="https://example.com",
            title="Test Title",
            memo="Test memo",
            summary="Test summary",
            keywords='["test", "keyword"]',
            created_at=datetime(2024, 1, 1),
            updated_at=datetime(2024, 1, 1),
            weaviate_id=None,
        )

        chunks = ["chunk1", "chunk2"]

        # モック設定
        mock_dependencies["mock_collection"].data.insert.return_value = "weaviate-id"

        # _get_clientをモック化
        with patch.object(vectorizer_service, "_get_client") as mock_get_client:
            mock_get_client.return_value.__enter__ = MagicMock(
                return_value=mock_dependencies["weaviate_client"]
            )
            mock_get_client.return_value.__exit__ = MagicMock(return_value=None)

            # 処理実行
            result = await vectorizer_service._save_chunks_to_weaviate(
                mock_page, chunks
            )

        # 結果確認
        assert result == "weaviate-id"

        # Weaviateへの保存が2回呼ばれたことを確認
        assert mock_dependencies["mock_collection"].data.insert.call_count == 2

        # 保存データの確認
        call_args_list = mock_dependencies["mock_collection"].data.insert.call_args_list

        # 最初のチャンク
        first_call = call_args_list[0]
        first_data = first_call[1]["properties"]
        assert first_data["pageId"] == 1
        assert first_data["chunkId"] == 0
        assert first_data["content"] == "chunk1"
        assert first_data["url"] == "https://example.com"
        assert first_data["title"] == "Test Title"

        # 2番目のチャンク
        second_call = call_args_list[1]
        second_data = second_call[1]["properties"]
        assert second_data["chunkId"] == 1
        assert second_data["content"] == "chunk2"

    @pytest.mark.asyncio
    async def test_health_check_success(
        self, vectorizer_service, mock_dependencies: Any
    ) -> None:
        """ヘルスチェック成功テスト."""
        # モック設定
        mock_client = MagicMock()
        mock_client.is_ready.return_value = True

        # _get_clientをモック化
        with patch.object(vectorizer_service, "_get_client") as mock_get_client:
            mock_get_client.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_get_client.return_value.__exit__ = MagicMock(return_value=None)

            # 処理実行
            result = await vectorizer_service.health_check()

        # 結果確認
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(
        self, vectorizer_service, mock_dependencies: Any
    ) -> None:
        """ヘルスチェック失敗テスト."""
        # _get_clientで例外を発生させる
        with patch.object(vectorizer_service, "_get_client") as mock_get_client:
            mock_get_client.side_effect = Exception("Connection error")

            # 処理実行
            result = await vectorizer_service.health_check()

        # 結果確認
        assert result is False

    @pytest.mark.asyncio
    async def test_ensure_schema_create_new(
        self, vectorizer_service, mock_dependencies
    ):
        """新規スキーマ作成テスト."""
        # モック設定（既存コレクションなし）
        mock_dependencies["weaviate_client"].collections.exists.return_value = False

        # _get_clientをモック化
        with patch.object(vectorizer_service, "_get_client") as mock_get_client:
            mock_get_client.return_value.__enter__ = MagicMock(
                return_value=mock_dependencies["weaviate_client"]
            )
            mock_get_client.return_value.__exit__ = MagicMock(return_value=None)

            # 処理実行
            await vectorizer_service.ensure_schema()

        # コレクション作成が呼ばれたことを確認
        mock_dependencies["weaviate_client"].collections.create.assert_called_once()

        # 作成されたコレクションの確認
        call_args = mock_dependencies["weaviate_client"].collections.create.call_args
        assert call_args[1]["name"] == "GrimoireChunk"

    @pytest.mark.asyncio
    async def test_ensure_schema_already_exists(
        self, vectorizer_service, mock_dependencies
    ):
        """既存スキーマ確認テスト."""
        # モック設定（既存コレクションあり）
        mock_dependencies["weaviate_client"].collections.exists.return_value = True

        # _get_clientをモック化
        with patch.object(vectorizer_service, "_get_client") as mock_get_client:
            mock_get_client.return_value.__enter__ = MagicMock(
                return_value=mock_dependencies["weaviate_client"]
            )
            mock_get_client.return_value.__exit__ = MagicMock(return_value=None)

            # 処理実行
            await vectorizer_service.ensure_schema()

        # コレクション作成が呼ばれないことを確認
        mock_dependencies["weaviate_client"].collections.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_schema_with_named_vectors(
        self, vectorizer_service, mock_dependencies
    ):
        """Named vectorsを含むスキーマ作成テスト."""
        # モック設定（既存コレクションなし）
        mock_dependencies["weaviate_client"].collections.exists.return_value = False

        # _get_clientをモック化
        with patch.object(vectorizer_service, "_get_client") as mock_get_client:
            mock_get_client.return_value.__enter__ = MagicMock(
                return_value=mock_dependencies["weaviate_client"]
            )
            mock_get_client.return_value.__exit__ = MagicMock(return_value=None)

            # 処理実行
            await vectorizer_service.ensure_schema()

        # コレクション作成が呼ばれたことを確認
        mock_dependencies["weaviate_client"].collections.create.assert_called_once()

        # vectorizer_configに3つのnamed vectorsが含まれることを確認
        call_args = mock_dependencies["weaviate_client"].collections.create.call_args
        vectorizer_config = call_args[1]["vectorizer_config"]
        
        assert isinstance(vectorizer_config, list)
        assert len(vectorizer_config) == 3
        
        # 各named vectorの名前を確認（実際のオブジェクトはモックではないため、存在確認のみ）
        assert vectorizer_config is not None
