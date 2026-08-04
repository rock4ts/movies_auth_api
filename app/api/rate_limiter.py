import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from fastapi import HTTPException, Request, status
from opentelemetry import trace
from redis import RedisError
from redis.asyncio import Redis

from app.core.config import rate_limit_settings
from app.core.request_context import get_client_ip

from .exceptions import RateLimitHttpException

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


_INCR_WITH_TTL_SCRIPT = """
local current = redis.call("INCR", KEYS[1])
if current == 1 then
    redis.call("PEXPIRE", KEYS[1], ARGV[1])
end
local ttl = redis.call("PTTL", KEYS[1])
return {current, ttl}
"""


@dataclass(frozen=True, slots=True)
class RateLimitRule:
    name: str
    limit: int
    window_seconds: int


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int
    remaining: int
    current_count: int


class RateLimitStorageError(Exception):
    pass


def _to_int(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, bytes):
        return int(value.decode("utf-8"))
    if isinstance(value, str):
        return int(value)
    raise RateLimitStorageError("Unexpected rate limiter response type")


def ip_per_route_rule() -> RateLimitRule:
    return RateLimitRule(
        name="ip_per_route",
        limit=rate_limit_settings.ip_limit,
        window_seconds=rate_limit_settings.ip_window_seconds,
    )


async def enforce_rate_limit(
    request: Request,
    rule: RateLimitRule,
    identity: str,
    limiter: "RedisFixedWindowRateLimiter",
) -> None:
    if not rate_limit_settings.enabled:
        return

    try:
        result = await limiter.consume(rule=rule, identity=identity)
    except RateLimitStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rate limiter is temporarily unavailable",
        ) from exc
    if result.allowed:
        return

    logger.warning(
        "Rate limit exceeded: policy=%s identity=%s ip=%s retry_after=%s",
        rule.name,
        identity,
        get_client_ip(request),
        result.retry_after_seconds,
    )
    raise RateLimitHttpException(retry_after_seconds=result.retry_after_seconds)


class RedisFixedWindowRateLimiter:
    def __init__(self, redis: Redis):
        self.redis: Redis = redis

    async def consume(self, rule: RateLimitRule, identity: str) -> RateLimitResult:
        key = f"{rate_limit_settings.redis_prefix}:{rule.name}:{identity}"
        window_ms = max(1, rule.window_seconds * 1000)

        with tracer.start_as_current_span("rate_limit.consume") as span:
            span.set_attribute("rate_limit.key", key)
            span.set_attribute("rate_limit.rule", rule.name)
            span.set_attribute("rate_limit.limit", rule.limit)
            span.set_attribute("rate_limit.window_seconds", rule.window_seconds)
            try:
                raw_result = cast(
                    Sequence[object],
                    await self.redis.execute_command(
                        "EVAL", _INCR_WITH_TTL_SCRIPT, 1, key, window_ms
                    ),
                )
                current_count = _to_int(raw_result[0])
                ttl_ms = _to_int(raw_result[1])
            except RedisError as exc:
                span.set_attribute("rate_limit.storage_error", True)
                if rate_limit_settings.fail_open:
                    logger.warning("Rate limiter unavailable; allowing request: %s", exc)
                    return RateLimitResult(
                        allowed=True,
                        retry_after_seconds=0,
                        remaining=rule.limit,
                        current_count=0,
                    )
                raise RateLimitStorageError("Rate limiter storage unavailable") from exc

            ttl_ms = max(ttl_ms, 0)
            retry_after_seconds = math.ceil(ttl_ms / 1000) if ttl_ms > 0 else rule.window_seconds
            remaining = max(rule.limit - current_count, 0)
            allowed = current_count <= rule.limit

            span.set_attribute("rate_limit.allowed", allowed)
            span.set_attribute("rate_limit.current_count", current_count)
            span.set_attribute("rate_limit.remaining", remaining)
            span.set_attribute("rate_limit.retry_after_seconds", retry_after_seconds)
            return RateLimitResult(
                allowed=allowed,
                retry_after_seconds=retry_after_seconds,
                remaining=remaining,
                current_count=current_count,
            )
