"""Additional tests for keywords filter handling."""

from unittest.mock import patch

import pytest
from grimoire_api.services.search_service import SearchService


class TestSearchServiceKeywords:
    """キーワードフィルター追加テスト."""

    @pytest.fixture
    def search_service(self) -> SearchService:
        """SearchServiceフィクスチャ."""
        return SearchService(weaviate_host="test-host", weaviate_port=8080)

    def test_build_weaviate_filter_keywords_string(
        self, search_service: SearchService
    ) -> None:
        """文字列キーワードフィルター構築テスト."""
        filters = {"keywords": "single_keyword"}

        with patch("weaviate.classes.query.Filter") as mock_filter:
            mock_filter.by_property.return_value.contains_any.return_value = (
                "keywords_filter"
            )

            result = search_service._build_weaviate_filter(filters)

            mock_filter.by_property.assert_called_with("keywords")
            mock_filter.by_property.return_value.contains_any.assert_called_with(
                ["single_keyword"]
            )
            assert result == "keywords_filter"

    def test_build_weaviate_filter_keywords_empty_list(
        self, search_service: SearchService
    ) -> None:
        """空配列キーワードフィルター構築テスト."""
        filters: dict[str, list[str]] = {"keywords": []}

        result = search_service._build_weaviate_filter(filters)

        assert result is None

    def test_build_weaviate_filter_keywords_empty_string(
        self, search_service: SearchService
    ) -> None:
        """空文字列キーワードフィルター構築テスト."""
        filters: dict[str, str] = {"keywords": ""}

        result = search_service._build_weaviate_filter(filters)

        assert result is None
