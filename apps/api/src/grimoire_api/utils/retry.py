"""Bounded retry helpers for calls to external services."""

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from .metrics import external_api_attempts, external_api_retries

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetryPolicy:
    """Configuration for one bounded external-service operation."""

    attempts: int
    backoff_base: float
    backoff_max: float
    jitter: float
    retry_after_max: float

    def delay(self, attempt: int, retry_after: float | None = None) -> float:
        """Return a capped exponential delay with additive jitter."""
        if retry_after is not None:
            return min(max(retry_after, 0.0), self.retry_after_max)
        exponential = float(
            min(self.backoff_base * (2 ** (attempt - 1)), self.backoff_max)
        )
        return exponential + float(random.uniform(0.0, self.jitter))


def parse_retry_after(value: str | None) -> float | None:
    """Parse Retry-After seconds or an HTTP date without raising."""
    if not value:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=UTC)
            return max((retry_at - datetime.now(UTC)).total_seconds(), 0.0)
        except (TypeError, ValueError, OverflowError):
            return None


async def retry_external_call[T](
    operation: Callable[[], Awaitable[T]],
    *,
    service: str,
    operation_name: str,
    policy: RetryPolicy,
    classify_error: Callable[[Exception], tuple[bool, str, float | None]],
) -> T:
    """Execute an operation and retry only errors explicitly classified transient."""
    for attempt in range(1, policy.attempts + 1):
        try:
            result = await operation()
        except Exception as error:
            retryable, reason, retry_after = classify_error(error)
            final = not retryable or attempt >= policy.attempts
            attributes = {
                "service": service,
                "operation": operation_name,
                "outcome": "failed_final" if final else "failed_retryable",
                "reason": reason,
            }
            external_api_attempts.add(1, attributes)
            logger.warning(
                "External service attempt failed",
                extra={
                    "event": "external_service.attempt.failed",
                    "service": service,
                    "operation": operation_name,
                    "attempt": attempt,
                    "max_attempts": policy.attempts,
                    "retryable": retryable,
                    "reason": reason,
                    "final": final,
                },
            )
            if final:
                raise
            delay = policy.delay(attempt, retry_after)
            external_api_retries.add(
                1,
                {
                    "service": service,
                    "operation": operation_name,
                    "reason": reason,
                },
            )
            logger.info(
                "Retrying external service call",
                extra={
                    "event": "external_service.retry.scheduled",
                    "service": service,
                    "operation": operation_name,
                    "attempt": attempt + 1,
                    "max_attempts": policy.attempts,
                    "reason": reason,
                    "delay_seconds": delay,
                },
            )
            await asyncio.sleep(delay)
        else:
            external_api_attempts.add(
                1,
                {
                    "service": service,
                    "operation": operation_name,
                    "outcome": "succeeded",
                    "reason": "none",
                },
            )
            return result
    raise RuntimeError("retry loop exhausted unexpectedly")
