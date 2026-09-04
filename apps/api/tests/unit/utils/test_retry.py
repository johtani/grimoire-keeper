"""Tests for bounded external-service retries."""

from unittest.mock import AsyncMock, patch

import pytest
from grimoire_api.utils.retry import RetryPolicy, parse_retry_after, retry_external_call


def policy(attempts: int = 3) -> RetryPolicy:
    return RetryPolicy(attempts, 1, 10, 0, 5)


@pytest.mark.asyncio
async def test_retries_transient_failure_and_honors_retry_after() -> None:
    operation = AsyncMock(side_effect=[TimeoutError(), "ok"])

    with patch(
        "grimoire_api.utils.retry.asyncio.sleep", new_callable=AsyncMock
    ) as sleep:
        result = await retry_external_call(
            operation,
            service="test",
            operation_name="read",
            policy=policy(),
            classify_error=lambda error: (True, "timeout", 20.0),
        )

    assert result == "ok"
    assert operation.await_count == 2
    sleep.assert_awaited_once_with(5)


@pytest.mark.asyncio
async def test_does_not_retry_permanent_failure() -> None:
    operation = AsyncMock(side_effect=ValueError("invalid"))

    with pytest.raises(ValueError, match="invalid"):
        await retry_external_call(
            operation,
            service="test",
            operation_name="read",
            policy=policy(),
            classify_error=lambda error: (False, "permanent", None),
        )

    operation.assert_awaited_once()


def test_parse_retry_after_supports_seconds_and_rejects_invalid_value() -> None:
    assert parse_retry_after("2.5") == 2.5
    assert parse_retry_after("invalid") is None
