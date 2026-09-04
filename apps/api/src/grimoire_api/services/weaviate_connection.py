"""Weaviate connection lifecycle management."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

import weaviate
from weaviate.config import AdditionalConfig, Timeout
from weaviate.exceptions import (
    WeaviateConnectionError,
    WeaviateGRPCUnavailableError,
    WeaviateStartUpError,
    WeaviateTimeoutError,
)

from ..utils.retry import RetryPolicy

logger = logging.getLogger(__name__)

ConnectionCallback = Callable[[weaviate.WeaviateClient], Awaitable[None]]
DisconnectionCallback = Callable[[], Awaitable[None]]


class WeaviateConnectionManager:
    """Keep a ready Weaviate client available and reconnect after failures."""

    def __init__(
        self,
        host: str,
        port: int,
        api_key: str,
        startup_attempts: int = 12,
        startup_interval: float = 5.0,
        startup_timeout: float = 60.0,
        connect_timeout: float = 5.0,
        query_timeout: float = 30.0,
        insert_timeout: float = 90.0,
        monitor_interval: float = 5.0,
        retry_backoff_base: float = 1.0,
        retry_backoff_max: float = 10.0,
        retry_jitter: float = 0.5,
        retry_after_max: float = 30.0,
        on_connected: ConnectionCallback | None = None,
        on_disconnected: DisconnectionCallback | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.api_key = api_key
        self.startup_attempts = startup_attempts
        self.startup_interval = startup_interval
        self.startup_timeout = startup_timeout
        self.connect_timeout = connect_timeout
        self.query_timeout = query_timeout
        self.insert_timeout = insert_timeout
        self.monitor_interval = monitor_interval
        self.retry_policy = RetryPolicy(
            attempts=startup_attempts,
            backoff_base=retry_backoff_base,
            backoff_max=retry_backoff_max,
            jitter=retry_jitter,
            retry_after_max=retry_after_max,
        )
        self.on_connected = on_connected
        self.on_disconnected = on_disconnected
        self.client: weaviate.WeaviateClient | None = None
        self._retry_connection = True
        self._monitor_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    @property
    def is_available(self) -> bool:
        """Return whether a ready client is currently registered."""
        return self.client is not None

    async def start(self) -> None:
        """Try the bounded startup connection, then begin background monitoring."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.startup_timeout
        attempt = 0
        for attempt in range(1, self.startup_attempts + 1):
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            if await self._connect(
                attempt, self.startup_attempts, remaining, deadline=deadline
            ):
                break
            if not self._retry_connection:
                logger.error("Weaviate connection failed permanently; not retrying")
                break
            if attempt < self.startup_attempts:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                delay = min(
                    self.retry_policy.delay(attempt),
                    self.startup_interval,
                    remaining,
                )
                logger.info(
                    "Retrying Weaviate connection in %.1f seconds",
                    delay,
                )
                await asyncio.sleep(delay)
        if self.client is None:
            logger.error(
                "Weaviate startup connection limit reached after at most %.1f seconds "
                "and %d attempts; continuing in degraded mode",
                self.startup_timeout,
                attempt,
            )

        self._monitor_task = asyncio.create_task(
            self._monitor(), name="weaviate-connection-monitor"
        )

    async def stop(self) -> None:
        """Stop monitoring and close the active client."""
        if self._monitor_task is not None:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
        await self._disconnect()

    def get_client(self) -> weaviate.WeaviateClient | None:
        """Return the active ready client, if any."""
        return self.client

    async def get_ready_client(self) -> weaviate.WeaviateClient | None:
        """Return the client only if it is currently ready."""
        client = self.client
        if client is None:
            return None
        try:
            ready = await asyncio.to_thread(client.is_ready)
        except Exception as exc:
            logger.warning("Weaviate request-time readiness check failed: %s", exc)
            ready = False
        if ready and client is self.client:
            return client
        logger.warning("Weaviate is unavailable; entering degraded mode")
        await self._disconnect(expected_client=client)
        return None

    async def _connect(
        self,
        attempt: int | None = None,
        limit: int | None = None,
        remaining: float | None = None,
        deadline: float | None = None,
    ) -> bool:
        async with self._lock:
            if self.client is not None:
                return True
            attempt_text = (
                f" (attempt {attempt}/{limit})" if attempt is not None and limit else ""
            )
            try:
                logger.info("Connecting to Weaviate%s", attempt_text)
                timeout = self.connect_timeout
                if remaining is not None:
                    timeout = min(timeout, max(remaining / 2, 0.001))
                client = await asyncio.to_thread(
                    weaviate.connect_to_local,
                    host=self.host,
                    port=self.port,
                    headers={"X-OpenAI-Api-Key": self.api_key},
                    additional_config=AdditionalConfig(
                        timeout=Timeout(
                            init=timeout,
                            query=self.query_timeout,
                            insert=self.insert_timeout,
                        )
                    ),
                )
                ready = await asyncio.to_thread(client.is_ready)
                if not ready:
                    raise RuntimeError("Weaviate reported that it is not ready")
                if self.on_connected is not None:
                    if deadline is None:
                        await self.on_connected(client)
                    else:
                        callback_timeout = deadline - asyncio.get_running_loop().time()
                        if callback_timeout <= 0:
                            raise TimeoutError("Weaviate startup deadline exceeded")
                        async with asyncio.timeout(callback_timeout):
                            await self.on_connected(client)
                self.client = client
                self._retry_connection = True
                logger.info("Weaviate connection established%s", attempt_text)
                return True
            except Exception as exc:
                if "client" in locals():
                    await self._close_client(client)
                self._retry_connection = self.is_retryable_error(exc) or isinstance(
                    exc, RuntimeError
                )
                logger.warning("Weaviate connection failed%s: %s", attempt_text, exc)
                return False

    @staticmethod
    def is_retryable_error(error: Exception) -> bool:
        """Return whether a Weaviate connection failure is transient."""
        current: BaseException | None = error
        while current is not None:
            if isinstance(
                current,
                (
                    TimeoutError,
                    OSError,
                    WeaviateConnectionError,
                    WeaviateGRPCUnavailableError,
                    WeaviateStartUpError,
                    WeaviateTimeoutError,
                ),
            ):
                return True
            current = current.__cause__
        return False

    async def _disconnect(
        self, expected_client: weaviate.WeaviateClient | None = None
    ) -> None:
        async with self._lock:
            client = self.client
            if client is None or (
                expected_client is not None and client is not expected_client
            ):
                return
            self.client = None
            if self.on_disconnected is not None:
                try:
                    await self.on_disconnected()
                except Exception:
                    logger.exception("Weaviate disconnection callback failed")
            await self._close_client(client)

    async def _close_client(self, client: weaviate.WeaviateClient) -> None:
        """Close a client without allowing cleanup errors to stop recovery."""
        try:
            await asyncio.to_thread(client.close)
            logger.info("Weaviate client closed")
        except Exception:
            logger.exception("Failed to close Weaviate client")

    async def _monitor(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.monitor_interval)
                client = self.client
                if client is None:
                    if self._retry_connection:
                        logger.info("Attempting background Weaviate reconnection")
                        await self._connect()
                    continue
                if await self.get_ready_client() is None:
                    await self._connect()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unexpected Weaviate monitor error; retrying")
