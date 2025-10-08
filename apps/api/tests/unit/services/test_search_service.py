"""Tests for SearchService."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from grimoire_api.services.search_service import SearchService
from grimoire_api.utils.exceptions import VectorizerError


class TestSearchService:
    """SearchServiceテストクラス."""

    @pytest.fixture
    def search_service(self) -> SearchService:
        """SearchServiceフィクスチャ."""
        return SearchService(weaviate_host="test-host", weaviate_port=8080)

    def test_init_default_values(self: Any) -> None:
        """デフォルト値での初期化テスト."""
        service = SearchService()
        assert service.weaviate_host == "weaviate"  # settings.WEAVIATE_HOST
        assert service.weaviate_port == 8089

    def test_init_custom_values(self: Any) -> None:
        """カスタム値での初期化テスト."""
        service = SearchService(weaviate_host="custom-host", weaviate_port=9090)
        assert service.weaviate_host == "custom-host"
        assert service.weaviate_port == 9090

    @pytest.mark.asyncio
    async def test_vector_search_without_filters(
        self, search_service: SearchService
    ) -> None:
        """フィルターなしのベクトル検索テスト."""
        # モックレスポンス
        mock_obj = MagicMock()
        mock_obj.metadata.certainty = 0.85
        mock_obj.properties = {
            "pageId": 1,
            "chunkId": 0,
            "url": "https://example.com",
            "title": "Test Title",
            "content": "Test content",
            "summary": "Test summary",
            "keywords": ["test", "example"],
            "createdAt": "2023-01-01T00:00:00Z",
        }

        mock_response = MagicMock()
        mock_response.objects = [mock_obj]

        mock_collection = MagicMock()
        mock_collection.query.near_text.return_value = mock_response

        mock_client = MagicMock()
        mock_client.collections.get.return_value = mock_collection
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch.object(search_service, "_get_client", return_value=mock_client):
            results = await search_service.vector_search("test query", limit=5)

        assert len(results) == 1
        assert results[0].page_id == 1
        assert results[0].url == "https://example.com"
        assert results[0].score == 0.85

        # near_textが正しいパラメータで呼ばれたことを確認
        mock_collection.query.near_text.assert_called_once()
        call_args = mock_collection.query.near_text.call_args
        assert call_args[1]["query"] == "test query"
        assert call_args[1]["target_vector"] == "content_vector"
        assert call_args[1]["limit"] == 5
        assert call_args[1]["filters"] is None

    @pytest.mark.asyncio
    async def test_vector_search_with_filters(
        self, search_service: SearchService
    ) -> None:
        """フィルター付きのベクトル検索テスト."""
        # モックレスポンス
        mock_obj = MagicMock()
        mock_obj.metadata.certainty = 0.90
        mock_obj.properties = {
            "pageId": 2,
            "chunkId": 1,
            "url": "https://filtered.com",
            "title": "Filtered Title",
            "content": "Filtered content",
            "summary": "Filtered summary",
            "keywords": ["filtered", "test"],
            "createdAt": "2023-06-01T00:00:00Z",
        }

        mock_response = MagicMock()
        mock_response.objects = [mock_obj]

        mock_collection = MagicMock()
        mock_collection.query.near_text.return_value = mock_response

        mock_client = MagicMock()
        mock_client.collections.get.return_value = mock_collection
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        filters = {
            "url": "filtered",
            "keywords": ["test", "example"],
            "date_from": "2023-01-01",
            "date_to": "2023-12-31",
        }

        with patch.object(search_service, "_get_client", return_value=mock_client):
            results = await search_service.vector_search(
                "filtered query", limit=3, filters=filters
            )

        assert len(results) == 1
        assert results[0].page_id == 2
        assert results[0].url == "https://filtered.com"
        assert results[0].score == 0.90

        # near_textが正しいパラメータで呼ばれたことを確認
        mock_collection.query.near_text.assert_called_once()
        call_args = mock_collection.query.near_text.call_args
        assert call_args[1]["query"] == "filtered query"
        assert call_args[1]["target_vector"] == "content_vector"
        assert call_args[1]["limit"] == 3
        assert call_args[1]["filters"] is not None

    @pytest.mark.asyncio
    async def test_vector_search_error(self, search_service: SearchService) -> None:
        """ベクトル検索エラーテスト."""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(side_effect=Exception("Connection error"))
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch.object(search_service, "_get_client", return_value=mock_client):
            with pytest.raises(VectorizerError, match="Vector search error"):
                await search_service.vector_search("test query")

    @pytest.mark.asyncio
    async def test_vector_search_with_memo_vector(
        self, search_service: SearchService
    ) -> None:
        """メモベクトル指定のベクトル検索テスト."""
        # モックレスポンス
        mock_obj = MagicMock()
        mock_obj.metadata.certainty = 0.88
        mock_obj.properties = {
            "pageId": 5,
            "chunkId": 0,
            "url": "https://memo-search.com",
            "title": "Memo Search Test",
            "memo": "Important memo content",
            "content": "Content for memo search",
            "summary": "Summary for memo search",
            "keywords": ["memo", "important"],
            "createdAt": "2023-05-01T00:00:00Z",
        }

        mock_response = MagicMock()
        mock_response.objects = [mock_obj]

        mock_collection = MagicMock()
        mock_collection.query.near_text.return_value = mock_response

        mock_client = MagicMock()
        mock_client.collections.get.return_value = mock_collection
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch.object(search_service, "_get_client", return_value=mock_client):
            results = await search_service.vector_search(
                "memo query", limit=3, vector_name="memo_vector"
            )

        assert len(results) == 1
        assert results[0].page_id == 5
        assert results[0].url == "https://memo-search.com"
        assert results[0].score == 0.88

        # near_textが正しいパラメータで呼ばれたことを確認
        mock_collection.query.near_text.assert_called_once()
        call_args = mock_collection.query.near_text.call_args
        assert call_args[1]["query"] == "memo query"
        assert call_args[1]["target_vector"] == "memo_vector"
        assert call_args[1]["limit"] == 3
        assert call_args[1]["filters"] is None

    @pytest.mark.asyncio
    async def test_keyword_search(self, search_service: SearchService) -> None:
        """キーワード検索テスト."""
        # モックレスポンス
        mock_obj = MagicMock()
        mock_obj.metadata.certainty = None
        mock_obj.metadata.distance = 0.1
        mock_obj.properties = {
            "pageId": 3,
            "chunkId": 0,
            "url": "https://keyword.com",
            "title": "Keyword Title",
            "content": "Keyword content",
            "summary": "Keyword summary",
            "keywords": ["keyword", "search"],
            "createdAt": "2023-03-01T00:00:00Z",
        }

        mock_response = MagicMock()
        mock_response.objects = [mock_obj]

        mock_collection = MagicMock()
        mock_collection.query.fetch_objects.return_value = mock_response

        mock_client = MagicMock()
        mock_client.collections.get.return_value = mock_collection
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch.object(search_service, "_get_client", return_value=mock_client):
            results = await search_service.keyword_search(
                ["keyword", "search"], limit=10
            )

        assert len(results) == 1
        assert results[0].page_id == 3
        assert results[0].url == "https://keyword.com"
        assert results[0].score == 0.9  # 1.0 - 0.1

    def test_build_weaviate_filter_url(self, search_service: SearchService) -> None:
        """URLフィルター構築テスト."""
        filters = {"url": "example"}

        with patch("weaviate.classes.query.Filter") as mock_filter:
            mock_filter.by_property.return_value.like.return_value = "url_filter"

            result = search_service._build_weaviate_filter(filters)

            mock_filter.by_property.assert_called_with("url")
            mock_filter.by_property.return_value.like.assert_called_with("*example*")
            assert result == "url_filter"

    def test_build_weaviate_filter_keywords(
        self, search_service: SearchService
    ) -> None:
        """キーワードフィルター構築テスト."""
        filters = {"keywords": ["test", "example"]}

        with patch("weaviate.classes.query.Filter") as mock_filter:
            mock_filter.by_property.return_value.contains_any.return_value = (
                "keywords_filter"
            )

            result = search_service._build_weaviate_filter(filters)

            mock_filter.by_property.assert_called_with("keywords")
            mock_filter.by_property.return_value.contains_any.assert_called_with(
                ["test", "example"]
            )
            assert result == "keywords_filter"

    def test_build_weaviate_filter_date_range(
        self, search_service: SearchService
    ) -> None:
        """日付範囲フィルター構築テスト."""
        filters = {"date_from": "2023-01-01", "date_to": "2023-12-31"}

        with patch("weaviate.classes.query.Filter") as mock_filter:
            mock_from_filter = MagicMock()
            mock_to_filter = MagicMock()
            mock_filter.by_property.return_value.greater_or_equal.return_value = (
                mock_from_filter
            )
            mock_filter.by_property.return_value.less_or_equal.return_value = (
                mock_to_filter
            )
            mock_filter.all_of.return_value = "combined_filter"

            result = search_service._build_weaviate_filter(filters)

            assert mock_filter.by_property.call_count == 2
            mock_filter.all_of.assert_called_once_with(
                [mock_from_filter, mock_to_filter]
            )
            assert result == "combined_filter"

    def test_build_weaviate_filter_empty(self, search_service: SearchService) -> None:
        """空フィルター構築テスト."""
        filters: dict[str, Any] = {}
        result = search_service._build_weaviate_filter(filters)
        assert result is None

    def test_convert_search_results_v4_certainty(
        self, search_service: SearchService
    ) -> None:
        """検索結果変換テスト（certainty）."""
        mock_obj = MagicMock()
        mock_obj.metadata.certainty = 0.95
        mock_obj.metadata.distance = None
        mock_obj.properties = {
            "pageId": 1,
            "chunkId": 0,
            "url": "https://test.com",
            "title": "Test",
            "memo": "Test memo",
            "content": "Content",
            "summary": "Summary",
            "keywords": ["test"],
            "createdAt": "2023-01-01T00:00:00Z",
        }

        mock_response = MagicMock()
        mock_response.objects = [mock_obj]

        results = search_service._convert_search_results_v4(mock_response)

        assert len(results) == 1
        assert results[0].score == 0.95

    def test_convert_search_results_v4_distance(
        self, search_service: SearchService
    ) -> None:
        """検索結果変換テスト（distance）."""
        mock_obj = MagicMock()
        mock_obj.metadata.certainty = None
        mock_obj.metadata.distance = 0.2
        mock_obj.properties = {
            "pageId": 1,
            "chunkId": 0,
            "url": "https://test.com",
            "title": "Test",
            "memo": None,
            "content": "Content",
            "summary": "Summary",
            "keywords": ["test"],
            "createdAt": "2023-01-01T00:00:00Z",
        }

        mock_response = MagicMock()
        mock_response.objects = [mock_obj]

        results = search_service._convert_search_results_v4(mock_response)

        assert len(results) == 1
        assert results[0].score == 0.8  # 1.0 - 0.2
        assert results[0].memo is None

    @pytest.mark.asyncio
    async def test_vector_search_with_custom_vector(
        self, search_service: SearchService
    ) -> None:
        """カスタムベクトル指定のベクトル検索テスト."""
        # モックレスポンス
        mock_obj = MagicMock()
        mock_obj.metadata.certainty = 0.92
        mock_obj.properties = {
            "pageId": 4,
            "chunkId": 0,
            "url": "https://title-search.com",
            "title": "Title Search Test",
            "content": "Content for title search",
            "summary": "Summary for title search",
            "keywords": ["title", "search"],
            "createdAt": "2023-04-01T00:00:00Z",
        }

        mock_response = MagicMock()
        mock_response.objects = [mock_obj]

        mock_collection = MagicMock()
        mock_collection.query.near_text.return_value = mock_response

        mock_client = MagicMock()
        mock_client.collections.get.return_value = mock_collection
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch.object(search_service, "_get_client", return_value=mock_client):
            results = await search_service.vector_search(
                "title query", limit=5, vector_name="title_vector"
            )

        assert len(results) == 1
        assert results[0].page_id == 4
        assert results[0].url == "https://title-search.com"
        assert results[0].score == 0.92

        # near_textが正しいパラメータで呼ばれたことを確認
        mock_collection.query.near_text.assert_called_once()
        call_args = mock_collection.query.near_text.call_args
        assert call_args[1]["query"] == "title query"
        assert call_args[1]["target_vector"] == "title_vector"
        assert call_args[1]["limit"] == 5
        assert call_args[1]["filters"] is None
