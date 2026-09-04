"""Jina AI Reader client."""

import httpx
from opentelemetry.instrumentation.utils import suppress_http_instrumentation
from pydantic import ValidationError

from ..config import settings
from ..models.external import FetchedDocument
from ..utils.exceptions import JinaClientError
from ..utils.retry import RetryPolicy, parse_retry_after, retry_external_call

_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


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
        self._retry_policy = RetryPolicy(
            attempts=settings.JINA_RETRY_ATTEMPTS,
            backoff_base=settings.JINA_RETRY_BACKOFF_BASE,
            backoff_max=settings.JINA_RETRY_BACKOFF_MAX,
            jitter=settings.JINA_RETRY_JITTER,
            retry_after_max=settings.JINA_RETRY_AFTER_MAX,
        )
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
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=settings.JINA_CONNECT_TIMEOUT,
                    read=settings.JINA_READ_TIMEOUT,
                    write=settings.JINA_WRITE_TIMEOUT,
                    pool=settings.JINA_POOL_TIMEOUT,
                )
            )
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

            async def request() -> httpx.Response:
                # The target URL is embedded in the Jina request path. HTTPX records
                # transport exceptions after request hooks run, so suppress automatic
                # spans here to prevent exception events from leaking that URL.
                with suppress_http_instrumentation():
                    response = await client.get(
                        f"{self.base_url}/{url}", headers=self._headers
                    )
                response.raise_for_status()
                return response

            response = await retry_external_call(
                request,
                service="jina",
                operation_name="fetch_content",
                policy=self._retry_policy,
                classify_error=self._classify_error,
            )
            raw_response = response.json()
            if not isinstance(raw_response, dict):
                raise ValueError("response root must be an object")
            return FetchedDocument.from_jina_response(raw_response, source_url=url)

        except httpx.HTTPStatusError as e:
            raise JinaClientError(
                f"Jina API HTTP error {e.response.status_code}"
            ) from None
        except httpx.RequestError as e:
            raise JinaClientError(
                f"Jina API request error ({type(e).__name__})"
            ) from None
        except (ValidationError, ValueError, TypeError) as e:
            fields = (
                sorted(
                    {str(error["loc"][-1]) for error in e.errors() if error.get("loc")}
                )
                if isinstance(e, ValidationError)
                else []
            )
            detail = f"; invalid fields: {', '.join(fields)}" if fields else ""
            raise JinaClientError(f"Invalid Jina response{detail}") from None
        except Exception:
            raise JinaClientError("Invalid Jina response") from None

    @staticmethod
    def _classify_error(error: Exception) -> tuple[bool, str, float | None]:
        """Classify Jina failures without exposing the requested URL."""
        if isinstance(error, httpx.HTTPStatusError):
            status = error.response.status_code
            retry_after = parse_retry_after(error.response.headers.get("Retry-After"))
            return status in _RETRYABLE_STATUS_CODES, f"http_{status}", retry_after
        if isinstance(error, httpx.TimeoutException):
            return True, "timeout", None
        if isinstance(error, httpx.TransportError):
            return True, "transport", None
        return False, "permanent", None

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
