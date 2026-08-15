"""Weaviate connection lifecycle management."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

import weaviate
from weaviate.config import AdditionalConfig, Timeout

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
        connect_timeout: float = 5.0,
        monitor_interval: float = 30.0,
        on_connected: ConnectionCallback | None = None,
        on_disconnected: DisconnectionCallback | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.api_key = api_key
        self.startup_attempts = startup_attempts
        self.startup_interval = startup_interval
        self.connect_timeout = connect_timeout
        self.monitor_interval = monitor_interval
        self.on_connected = on_connected
        self.on_disconnected = on_disconnected
        self.client: weaviate.WeaviateClient | None = None
        self._monitor_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    @property
    def is_available(self) -> bool:
        """Return whether a ready client is currently registered."""
        return self.client is not None

    async def start(self) -> None:
        """Try the bounded startup connection, then begin background monitoring."""
        for attempt in range(1, self.startup_attempts + 1):
            if await self._connect(attempt, self.startup_attempts):
                break
            if attempt < self.startup_attempts:
                logger.info(
                    "Retrying Weaviate connection in %.1f seconds",
                    self.startup_interval,
                )
                await asyncio.sleep(self.startup_interval)
        else:
            logger.error(
                "Weaviate startup connection retry limit reached after %d attempts; "
                "continuing in degraded mode",
                self.startup_attempts,
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

    async def _connect(
        self, attempt: int | None = None, limit: int | None = None
    ) -> bool:
        async with self._lock:
            if self.client is not None:
                return True
            attempt_text = (
                f" (attempt {attempt}/{limit})" if attempt is not None and limit else ""
            )
            try:
                logger.info("Connecting to Weaviate%s", attempt_text)
                client = await asyncio.to_thread(
                    weaviate.connect_to_local,
                    host=self.host,
                    port=self.port,
                    headers={"X-OpenAI-Api-Key": self.api_key},
                    additional_config=AdditionalConfig(
                        timeout=Timeout(init=self.connect_timeout)
                    ),
                )
                ready = await asyncio.to_thread(client.is_ready)
                if not ready:
                    raise RuntimeError("Weaviate reported that it is not ready")
                if self.on_connected is not None:
                    await self.on_connected(client)
                self.client = client
                logger.info("Weaviate connection established%s", attempt_text)
                return True
            except Exception as exc:
                if "client" in locals():
                    await asyncio.to_thread(client.close)
                logger.warning("Weaviate connection failed%s: %s", attempt_text, exc)
                return False

    async def _disconnect(self) -> None:
        async with self._lock:
            client = self.client
            if client is None:
                return
            self.client = None
            if self.on_disconnected is not None:
                await self.on_disconnected()
            await asyncio.to_thread(client.close)
            logger.info("Weaviate client closed")

    async def _monitor(self) -> None:
        while True:
            await asyncio.sleep(self.monitor_interval)
            client = self.client
            if client is None:
                logger.info("Attempting background Weaviate reconnection")
                await self._connect()
                continue
            try:
                ready = await asyncio.to_thread(client.is_ready)
            except Exception as exc:
                logger.warning("Weaviate readiness check failed: %s", exc)
                ready = False
            if not ready:
                logger.warning("Weaviate connection lost; entering degraded mode")
                await self._disconnect()
                await self._connect()
