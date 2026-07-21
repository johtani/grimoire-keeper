"""Jina AI Reader client."""

import httpx
from pydantic import ValidationError

from ..config import settings
from ..models.external import FetchedDocument
from ..utils.exceptions import JinaClientError

_TIMEOUT = 60.0


class JinaClient:
    """Jina AI Reader クライアント."""

    def __init__(self, api_key: str | None = None):
        """初期化.

        Args:
            api_key: Jina API キー
        """
        self.api_key = api_key or settings.JINA_API_KEY
        self.base_url = "https://r.jina.ai"
        self._client: httpx.AsyncClient | None = None
        self._headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "X-Return-Format": "markdown",
            "X-Md-Link-Style": "discarded",
            "X-With-Images-Summary": "true",
            "X-With-Links-Summary": "true",
            "X-With-Generated-Alt": "true",
        }

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=_TIMEOUT)
        return self._client

    async def close(self) -> None:
        """httpx クライアントを閉じる."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def fetch_content(self, url: str) -> FetchedDocument:
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

        client = await self._get_client()
        try:
            response = await client.get(f"{self.base_url}/{url}", headers=self._headers)
            response.raise_for_status()
            raw_response = response.json()
            if not isinstance(raw_response, dict):
                raise ValueError("response root must be an object")
            return FetchedDocument.from_jina_response(raw_response, source_url=url)

        except httpx.HTTPStatusError as e:
            raise JinaClientError(f"Jina API HTTP error {e.response.status_code}")
        except httpx.RequestError as e:
            raise JinaClientError(f"Jina API request error: {str(e)}")
        except (ValidationError, ValueError, TypeError) as e:
            fields = (
                sorted(
                    {str(error["loc"][-1]) for error in e.errors() if error.get("loc")}
                )
                if isinstance(e, ValidationError)
                else []
            )
            detail = f"; invalid fields: {', '.join(fields)}" if fields else ""
            raise JinaClientError(f"Invalid Jina response{detail}") from e
        except Exception as e:
            raise JinaClientError("Invalid Jina response") from e

    async def health_check(self) -> bool:
        """ヘルスチェック.

        Returns:
            APIが利用可能かどうか
        """
        try:
            await self.fetch_content("https://example.com")
            return True
        except JinaClientError:
            return False
