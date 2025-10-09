"""バックエンドAPI連携クライアント"""

import os
from typing import Any

import httpx


class ApiClient:
    """グリモワールAPI連携クライアント"""

    def __init__(self):
        self.base_url = os.environ.get("BACKEND_API_URL", "http://localhost:8000")
        self.timeout = 30.0

    async def process_url(self, url: str, memo: str | None = None) -> dict[str, Any]:
        """URL処理リクエスト"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            payload = {"url": url}
            if memo:
                payload["memo"] = memo

            response = await client.post(
                f"{self.base_url}/api/v1/process-url", json=payload
            )
            response.raise_for_status()
            return response.json()

    async def search_content(self, query: str, limit: int = 5) -> dict[str, Any]:
        """コンテンツ検索"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/search",
                json={"query": query, "limit": limit, "vector_name": "title_vector"}
            )
            response.raise_for_status()
            return response.json()

    async def get_process_status(self, page_id: int) -> dict[str, Any]:
        """処理状況確認"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/process-status/{page_id}"
            )
            response.raise_for_status()
            return response.json()

    async def health_check(self) -> bool:
        """ヘルスチェック"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/v1/health")
                return response.status_code == 200
        except Exception:
            return False
