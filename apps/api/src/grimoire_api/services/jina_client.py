"""Jina AI Reader client."""

from typing import Any

import httpx

from ..config import settings
from ..utils.exceptions import JinaClientError


class JinaClient:
    """Jina AI Reader クライアント."""

    def __init__(self, api_key: str | None = None):
        """初期化.

        Args:
            api_key: Jina API キー
        """
        self.api_key = api_key or settings.JINA_API_KEY
        self.base_url = "https://r.jina.ai"

    async def fetch_content(self, url: str) -> dict[str, Any]:
        """URL内容取得.

        Args:
            url: 取得対象のURL

        Returns:
            Jina AI Readerのレスポンス

        Raises:
            JinaClientError: API呼び出しエラー
        """
        if not self.api_key or self.api_key.strip() == "":
            raise JinaClientError("Jina API key is not configured")

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "X-Return-Format": "markdown",
            "X-Md-Link-Style": "discarded",
            "X-With-Images-Summary": "true",
            "X-With-Links-Summary": "true",
            "X-With-Generated-Alt": "true",
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.base_url}/{url}", headers=headers, timeout=60.0
                )
                response.raise_for_status()
                return response.json()  # type: ignore[no-any-return]

            except httpx.HTTPStatusError as e:
                raise JinaClientError(
                    f"Jina API HTTP error {e.response.status_code}: {e.response.text}"
                )
            except httpx.RequestError as e:
                raise JinaClientError(f"Jina API request error: {str(e)}")
            except Exception as e:
                raise JinaClientError(f"Jina API unexpected error: {str(e)}")

    async def health_check(self) -> bool:
        """ヘルスチェック.

        Returns:
            APIが利用可能かどうか
        """
        try:
            # 簡単なテストURL
            test_url = "https://example.com"
            await self.fetch_content(test_url)
            return True
        except JinaClientError:
            return False
