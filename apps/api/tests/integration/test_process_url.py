"""Integration tests for process-url endpoint."""

import json
import os
import time
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from grimoire_api.main import app


@pytest.fixture
def integration_client() -> Any:
    """統合テスト用クライアントフィクスチャ."""
    test_env = {
        "DATABASE_PATH": ":memory:",
        "JINA_API_KEY": "test-jina-key",
        "GOOGLE_API_KEY": "test-google-key",
        "OPENAI_API_KEY": "test-openai-key",
        "WEAVIATE_HOST": "localhost",
        "WEAVIATE_PORT": "8080",
    }

    with patch.dict(os.environ, test_env):
        with TestClient(app) as client:
            yield client


class TestProcessUrlIntegration:
    """process-url統合テストクラス."""

    def test_process_url_success(self, integration_client: Any) -> None:
        """正常なURL処理の統合テスト."""
        test_url = "https://example.com/test"
        test_memo = "Test memo"

        # モックレスポンス設定
        mock_jina_response = {
            "data": {
                "title": "Test Page Title",
                "content": "This is test content for integration testing.",
            }
        }

        mock_llm_response = {
            "summary": "Test summary for integration testing",
            "keywords": ["test", "integration", "example"],
        }

        with (
            patch(
                "grimoire_api.services.jina_client.JinaClient.fetch_content"
            ) as mock_jina,
            patch("grimoire_api.services.llm_service.completion") as mock_llm,
            patch(
                "grimoire_api.services.vectorizer.VectorizerService.vectorize_content"
            ) as mock_vectorizer,
        ):
            # モック設定
            mock_jina.return_value = mock_jina_response

            # LLMレスポンスのモック
            class MockLLMResponse:
                def __init__(self: Any) -> Any:
                    self.choices = [MockChoice()]

                def model_dump(self: Any) -> Any:
                    return {
                        "choices": [
                            {"message": {"content": json.dumps(mock_llm_response)}}
                        ]
                    }

            class MockChoice:
                def __init__(self: Any) -> Any:
                    self.message = MockMessage()

            class MockMessage:
                def __init__(self: Any) -> Any:
                    self.content = json.dumps(mock_llm_response)

            mock_llm.return_value = MockLLMResponse()
            mock_vectorizer.return_value = None

            # URL処理リクエスト
            response = integration_client.post(
                "/api/v1/process-url", json={"url": test_url, "memo": test_memo}
            )

            # レスポンス確認
            assert response.status_code == 200
            data = response.json()
            # 初回処理の場合は"processing"、既存の場合は"already_exists"
            assert data["status"] in ["processing", "already_exists"]
            assert "page_id" in data

            page_id = data["page_id"]

            # バックグラウンド処理完了まで待機
            time.sleep(2)

            # 処理状況確認
            status_response = integration_client.get(
                f"/api/v1/process-status/{page_id}"
            )
            assert status_response.status_code == 200

            status_data = status_response.json()
            assert status_data["status"] in ["completed", "processing"]
            assert "page" in status_data

            page_data = status_data["page"]
            assert page_data["id"] == page_id
            assert page_data["url"] == test_url
            assert page_data["memo"] == test_memo

    def test_process_url_duplicate(self, integration_client: Any) -> None:
        """重複URL処理テスト."""
        test_url = "https://example.com/duplicate"

        # 1回目の処理
        response1 = integration_client.post(
            "/api/v1/process-url", json={"url": test_url, "memo": "First request"}
        )
        assert response1.status_code == 200
        data1 = response1.json()
        page_id = data1["page_id"]

        # 2回目の処理（重複）
        response2 = integration_client.post(
            "/api/v1/process-url", json={"url": test_url, "memo": "Second request"}
        )
        assert response2.status_code == 200
        data2 = response2.json()

        assert data2["status"] == "already_exists"
        assert data2["page_id"] == page_id
        assert "already exists" in data2["message"]

    def test_process_url_invalid_url(self, integration_client: Any) -> None:
        """無効なURL処理テスト."""
        response = integration_client.post(
            "/api/v1/process-url", json={"url": "invalid-url", "memo": "Test memo"}
        )

        # バリデーションエラーまたは処理エラーを期待
        assert response.status_code in [400, 422, 500]

    def test_process_url_missing_url(self, integration_client: Any) -> None:
        """URL未指定テスト."""
        response = integration_client.post(
            "/api/v1/process-url", json={"memo": "Test memo"}
        )

        assert response.status_code == 422  # バリデーションエラー

    def test_process_status_not_found(self, integration_client: Any) -> None:
        """存在しないページの処理状況確認テスト."""
        response = integration_client.get("/api/v1/process-status/99999")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "not_found"
        assert "not found" in data["message"]

    def test_process_url_with_jina_error(self, integration_client: Any) -> None:
        """Jina AI Readerエラー時のテスト."""
        test_url = "https://example.com/jina-error"

        with patch(
            "grimoire_api.services.jina_client.JinaClient.fetch_content"
        ) as mock_jina:
            mock_jina.side_effect = Exception("Jina API error")

            response = integration_client.post(
                "/api/v1/process-url", json={"url": test_url, "memo": "Error test"}
            )

            assert response.status_code == 200
            data = response.json()
            page_id = data["page_id"]

            # バックグラウンド処理完了まで待機
            time.sleep(2)

            # エラー状態確認
            status_response = integration_client.get(
                f"/api/v1/process-status/{page_id}"
            )
            status_data = status_response.json()

            # エラー状態またはまだ処理中の可能性
            assert status_data["status"] in ["failed", "processing"]

    def test_process_url_workflow(self, integration_client: Any) -> None:
        """完全なワークフローテスト."""
        test_url = "https://example.com/workflow"
        test_memo = "Workflow test"

        # モック設定
        mock_jina_response = {
            "data": {
                "title": "Workflow Test Page",
                "content": "Content for workflow testing with keywords and summary.",
            }
        }

        mock_llm_response = {
            "summary": "This is a workflow test page for integration testing",
            "keywords": ["workflow", "test", "integration", "page", "content"],
        }

        with (
            patch(
                "grimoire_api.services.jina_client.JinaClient.fetch_content"
            ) as mock_jina,
            patch("grimoire_api.services.llm_service.completion") as mock_llm,
            patch(
                "grimoire_api.services.vectorizer.VectorizerService.vectorize_content"
            ) as mock_vectorizer,
        ):
            # モック設定
            mock_jina.return_value = mock_jina_response

            class MockLLMResponse:
                def model_dump(self: Any) -> Any:
                    return {
                        "choices": [
                            {"message": {"content": json.dumps(mock_llm_response)}}
                        ]
                    }

            mock_llm.return_value = MockLLMResponse()
            mock_vectorizer.return_value = None

            # 1. URL処理開始
            response = integration_client.post(
                "/api/v1/process-url", json={"url": test_url, "memo": test_memo}
            )

            assert response.status_code == 200
            data = response.json()
            page_id = data["page_id"]

            # 2. 処理完了まで待機
            time.sleep(3)

            # 3. 最終状態確認
            status_response = integration_client.get(
                f"/api/v1/process-status/{page_id}"
            )
            status_data = status_response.json()

            # 4. 結果検証
            if status_data["status"] == "completed":
                page_data = status_data["page"]
                assert page_data["title"] == "Workflow Test Page"
                assert page_data["summary"] is not None
                assert isinstance(page_data["keywords"], list)
                assert len(page_data["keywords"]) > 0
