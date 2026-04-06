"""Test vectorizer service."""

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from grimoire_api.config import settings
from grimoire_api.models.database import Page, ProcessingStep
from grimoire_api.services.vectorizer import VectorizerService
from grimoire_api.utils.exceptions import VectorizerError


class TestVectorizerService:
    """VectorizerServiceのテストクラス."""

    @pytest.fixture
    def mock_dependencies(self: Any) -> Any:
        """依存関係のモック."""
        mock_collection = MagicMock()
        # delete_many のデフォルトは削除対象なし (matches=0, failed=0) とする
        mock_delete_result = MagicMock()
        mock_delete_result.matches = 0
        mock_delete_result.failed = 0
        mock_collection.data.delete_many.return_value = mock_delete_result

        mock_collections = MagicMock()
        mock_collections.get.return_value = mock_collection
        mock_collections.exists.return_value = False

        mock_client = MagicMock()
        mock_client.collections = mock_collections
        mock_client.is_ready.return_value = True

        # PageRepositoryのモック
        mock_page_repo = MagicMock()
        mock_page_repo.get_page = AsyncMock()
        mock_page_repo.update_weaviate_id_and_step = AsyncMock()

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
            weaviate_client=mock_dependencies["weaviate_client"],
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
        mock_dependencies[
            "chunking_service"
        ].chunk_text_with_jina_data.return_value = mock_chunks
        mock_dependencies[
            "mock_collection"
        ].data.insert.return_value = "weaviate-id-123"

        # 処理実行
        await vectorizer_service.vectorize_content(page_id)

        # 各メソッドが呼ばれたことを確認
        mock_dependencies["page_repo"].get_page.assert_called_once_with(page_id)
        mock_dependencies["file_repo"].load_json_file.assert_called_once_with(page_id)
        mock_dependencies[
            "chunking_service"
        ].chunk_text_with_jina_data.assert_called_once_with(
            "This is test content for vectorization.", mock_jina_data
        )

        # Weaviateへの保存が3回呼ばれたことを確認
        assert mock_dependencies["mock_collection"].data.insert.call_count == 3

        # Weaviate IDと成功ステップのアトミック更新が呼ばれたことを確認
        mock_dependencies["page_repo"].update_weaviate_id_and_step.assert_called_once()
        call_args = mock_dependencies["page_repo"].update_weaviate_id_and_step.call_args
        assert call_args[0][0] == page_id  # page_id
        assert len(call_args[0][1]) == 36  # UUID形式の文字列長
        assert call_args[0][2] == ProcessingStep.VECTORIZED  # step

    @pytest.mark.asyncio
    async def test_vectorize_content_page_not_found(
        self, vectorizer_service, mock_dependencies
    ):
        """ページが見つからない場合のテスト."""
        page_id = 999

        # モック設定
        mock_dependencies["page_repo"].get_page.return_value = None

        # エラー確認
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
        mock_dependencies[
            "chunking_service"
        ].chunk_text_with_jina_data.return_value = []

        # エラー確認
        with pytest.raises(VectorizerError, match="No chunks generated from content"):
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

        # 処理実行
        result = await vectorizer_service._save_chunks_to_weaviate(mock_page, chunks)

        # 結果確認（UUID5で生成されたIDが返される）
        assert len(result) == 36  # UUID形式の文字列長
        assert "-" in result  # UUIDにはハイフンが含まれる

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
    async def test_delete_existing_chunks_failure(
        self, vectorizer_service, mock_dependencies: Any
    ) -> None:
        """_delete_existing_chunks が失敗時に例外を伝播するテスト."""
        mock_collection = MagicMock()
        mock_collection.data.delete_many.side_effect = Exception(
            "Weaviate delete error"
        )

        with pytest.raises(Exception, match="Weaviate delete error"):
            await vectorizer_service._delete_existing_chunks(mock_collection, 1)

    @pytest.mark.asyncio
    async def test_delete_existing_chunks_no_matches(
        self, vectorizer_service, mock_dependencies: Any
    ) -> None:
        """削除対象なし（matches=0）の場合はポーリングしないテスト."""
        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.matches = 0
        mock_result.failed = 0
        mock_collection.data.delete_many.return_value = mock_result

        with patch(
            "grimoire_api.services.vectorizer.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            await vectorizer_service._delete_existing_chunks(mock_collection, 1)

        mock_collection.query.fetch_objects.assert_not_called()
        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_existing_chunks_completes_on_first_check(
        self, vectorizer_service, mock_dependencies: Any
    ) -> None:
        """初回確認で削除完了する場合のテスト (sleep→check 順)."""
        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.matches = 3
        mock_result.failed = 0
        mock_collection.data.delete_many.return_value = mock_result

        # fetch_objects が空リストを返す（削除完了）
        mock_query_result = MagicMock()
        mock_query_result.objects = []
        mock_collection.query.fetch_objects.return_value = mock_query_result

        with patch(
            "grimoire_api.services.vectorizer.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            await vectorizer_service._delete_existing_chunks(mock_collection, 1)

        # sleep→check 順のため: sleep 1回 → check 1回 → 完了
        mock_collection.query.fetch_objects.assert_called_once()
        mock_sleep.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_existing_chunks_completes_after_retries(
        self, vectorizer_service, mock_dependencies: Any
    ) -> None:
        """数回リトライ後に削除完了する場合のテスト (sleep→check 順)."""
        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.matches = 2
        mock_result.failed = 0
        mock_collection.data.delete_many.return_value = mock_result

        # 最初の2回は残存オブジェクトあり、3回目で空
        remaining_with_objects = MagicMock()
        remaining_with_objects.objects = [MagicMock()]
        remaining_empty = MagicMock()
        remaining_empty.objects = []
        mock_collection.query.fetch_objects.side_effect = [
            remaining_with_objects,
            remaining_with_objects,
            remaining_empty,
        ]

        with patch(
            "grimoire_api.services.vectorizer.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            await vectorizer_service._delete_existing_chunks(mock_collection, 1)

        # sleep→check 順のため: sleep と check が同じ回数
        assert mock_collection.query.fetch_objects.call_count == 3
        assert mock_sleep.call_count == 3

    @pytest.mark.asyncio
    async def test_delete_existing_chunks_timeout(
        self, vectorizer_service, mock_dependencies: Any
    ) -> None:
        """タイムアウト（10回超え）で VectorizerError が発生するテスト."""
        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.matches = 5
        mock_result.failed = 0
        mock_collection.data.delete_many.return_value = mock_result

        # 常に残存オブジェクトあり（削除が完了しない）
        remaining_with_objects = MagicMock()
        remaining_with_objects.objects = [MagicMock()]
        mock_collection.query.fetch_objects.return_value = remaining_with_objects

        with patch(
            "grimoire_api.services.vectorizer.asyncio.sleep", new_callable=AsyncMock
        ):
            with pytest.raises(
                VectorizerError, match="did not complete within timeout"
            ):
                await vectorizer_service._delete_existing_chunks(mock_collection, 1)

        assert mock_collection.query.fetch_objects.call_count == 10

    @pytest.mark.asyncio
    async def test_save_chunks_uses_asyncio_to_thread(
        self, vectorizer_service, mock_dependencies: Any
    ) -> None:
        """_save_chunks_to_weaviate が asyncio.to_thread で insert することを確認."""
        mock_page = Page(
            id=1,
            url="https://example.com",
            title="Test Title",
            memo=None,
            summary=None,
            keywords=None,
            created_at=datetime(2024, 1, 1),
            updated_at=datetime(2024, 1, 1),
            weaviate_id=None,
        )
        chunks = ["chunk1", "chunk2"]

        # asyncio.to_thread をパッチして同期的に実行しつつ呼び出しを記録する
        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        with patch(
            "grimoire_api.services.vectorizer.asyncio.to_thread",
            side_effect=fake_to_thread,
        ) as mock_to_thread:
            await vectorizer_service._save_chunks_to_weaviate(mock_page, chunks)

        # asyncio.to_thread が _insert_chunks_sync で呼ばれたことを確認
        from grimoire_api.services.vectorizer import _insert_chunks_sync

        insert_calls = [
            call
            for call in mock_to_thread.call_args_list
            if call[0][0] is _insert_chunks_sync
        ]
        assert len(insert_calls) == 1

        # _insert_chunks_sync に渡されたオブジェクトリストが正しいことを確認
        _, objects_to_insert = insert_calls[0][0][1], insert_calls[0][0][2]
        assert len(objects_to_insert) == 2
        assert objects_to_insert[0][0]["content"] == "chunk1"
        assert objects_to_insert[1][0]["content"] == "chunk2"

    @pytest.mark.asyncio
    async def test_save_chunks_weaviate_delete_failure(
        self, vectorizer_service, mock_dependencies: Any
    ) -> None:
        """削除失敗時に VectorizerError が発生するテスト."""
        mock_page = Page(
            id=1,
            url="https://example.com",
            title="Test Title",
            memo=None,
            summary=None,
            keywords=None,
            created_at=datetime(2024, 1, 1),
            updated_at=datetime(2024, 1, 1),
            weaviate_id=None,
        )

        mock_dependencies["mock_collection"].data.delete_many.side_effect = Exception(
            "Weaviate delete error"
        )

        with pytest.raises(VectorizerError, match="Failed to save chunks to Weaviate"):
            await vectorizer_service._save_chunks_to_weaviate(mock_page, ["chunk1"])

    @pytest.mark.asyncio
    async def test_health_check_success(
        self, vectorizer_service, mock_dependencies: Any
    ) -> None:
        """ヘルスチェック成功テスト."""
        mock_dependencies["weaviate_client"].is_ready.return_value = True

        result = await vectorizer_service.health_check()

        assert result is True
        mock_dependencies["weaviate_client"].is_ready.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_failure(
        self, vectorizer_service, mock_dependencies: Any
    ) -> None:
        """ヘルスチェック失敗テスト."""
        mock_dependencies["weaviate_client"].is_ready.side_effect = Exception(
            "Connection error"
        )

        result = await vectorizer_service.health_check()

        assert result is False

    @pytest.mark.asyncio
    async def test_ensure_schema_create_new(
        self, vectorizer_service, mock_dependencies
    ):
        """新規スキーマ作成テスト."""
        # モック設定（既存コレクションなし）
        mock_dependencies["weaviate_client"].collections.exists.return_value = False

        # 処理実行
        await vectorizer_service.ensure_schema()

        # コレクション作成が呼ばれたことを確認
        mock_dependencies["weaviate_client"].collections.create.assert_called_once()

        # 作成されたコレクションの確認
        call_args = mock_dependencies["weaviate_client"].collections.create.call_args
        assert call_args[1]["name"] == settings.WEAVIATE_COLLECTION_NAME

    @pytest.mark.asyncio
    async def test_ensure_schema_already_exists(
        self, vectorizer_service, mock_dependencies
    ):
        """既存スキーマ確認テスト."""
        # モック設定（既存コレクションあり）
        mock_dependencies["weaviate_client"].collections.exists.return_value = True

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

        # 処理実行
        await vectorizer_service.ensure_schema()

        # コレクション作成が呼ばれたことを確認
        mock_dependencies["weaviate_client"].collections.create.assert_called_once()

        # vector_configに3つのnamed vectorsが含まれることを確認
        call_args = mock_dependencies["weaviate_client"].collections.create.call_args
        vector_config = call_args[1]["vector_config"]

        assert isinstance(vector_config, list)
        assert len(vector_config) == 3
