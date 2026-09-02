"""バックエンドAPI連携クライアント"""

import os
from typing import Any, cast

import httpx
from pydantic import ValidationError

from ..models.api import ProcessStatusResponse


class ApiClientError(Exception):
    """Safe structured error returned by the backend API."""

    def __init__(
        self,
        code: str,
        request_id: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.request_id = request_id
        self.status_code = status_code


class ApiClient:
    """グリモワールAPI連携クライアント"""

    def __init__(self) -> None:
        self.base_url = os.environ.get("BACKEND_API_URL", "http://localhost:8000")
        self.timeout = 30.0

    async def _request(
        self, method: str, path: str, json: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                if method == "GET":
                    response = await client.get(f"{self.base_url}{path}")
                else:
                    response = await client.post(f"{self.base_url}{path}", json=json)
        except httpx.RequestError as exc:
            raise ApiClientError("connection_error") from exc

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            try:
                error = response.json().get("error", {})
            except (ValueError, AttributeError):
                error = {}
            raise ApiClientError(
                code=error.get("code", "api_error"),
                request_id=error.get("request_id"),
                status_code=response.status_code,
            ) from exc
        return cast(dict[str, Any], response.json())

    async def process_url(self, url: str, memo: str | None = None) -> dict[str, Any]:
        """URL処理リクエスト"""
        payload = {"url": url}
        if memo:
            payload["memo"] = memo
        return await self._request("POST", "/api/v1/process-url", payload)

    async def search_content(self, query: str, limit: int = 5) -> dict[str, Any]:
        """コンテンツ検索"""
        return await self._request(
            "POST",
            "/api/v1/search",
            {"query": query, "limit": limit, "vector_name": "title_vector"},
        )

    async def get_process_status(self, page_id: int) -> ProcessStatusResponse:
        """処理状況を取得し、Bot が依存する API 契約を検証する."""
        response = await self._request("GET", f"/api/v1/process-status/{page_id}")
        try:
            return ProcessStatusResponse.model_validate(response)
        except ValidationError as exc:
            raise ApiClientError("invalid_response") from exc

    async def health_check(self) -> bool:
        """ヘルスチェック"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/v1/health")
                return response.status_code == 200
        except Exception:
            return False
