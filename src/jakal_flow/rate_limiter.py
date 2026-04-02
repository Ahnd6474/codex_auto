from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
import math
import time

from .lru_ttl_cache import LruTtlCache


@dataclass(frozen=True, slots=True)
class TokenBucketRule:
    capacity: float
    refill_tokens_per_second: float

    def normalized(self) -> "TokenBucketRule":
        return TokenBucketRule(
            capacity=max(1.0, float(self.capacity)),
            refill_tokens_per_second=max(0.0, float(self.refill_tokens_per_second)),
        )


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int
    tokens_remaining: float


@dataclass(slots=True)
class _TokenBucketState:
    tokens: float
    updated_at_monotonic: float


class TokenBucketRateLimiter:
    def __init__(self, *, max_buckets: int = 1024, bucket_ttl_seconds: float = 300.0) -> None:
        self._buckets = LruTtlCache[str, _TokenBucketState](
            max_entries=max_buckets,
            ttl_seconds=bucket_ttl_seconds,
        )
        self._lock = Lock()

    def consume(
        self,
        bucket_id: str,
        *,
        rule: TokenBucketRule,
        cost: float = 1.0,
        now_monotonic: float | None = None,
    ) -> RateLimitDecision:
        normalized_rule = rule.normalized()
        normalized_cost = max(0.0, float(cost))
        now = time.monotonic() if now_monotonic is None else float(now_monotonic)
        with self._lock:
            previous = self._buckets.peek(bucket_id)
            available_tokens = normalized_rule.capacity
            updated_at = now
            if previous is not None:
                elapsed = max(0.0, now - previous.updated_at_monotonic)
                replenished = previous.tokens + (elapsed * normalized_rule.refill_tokens_per_second)
                available_tokens = min(normalized_rule.capacity, replenished)
                updated_at = now
            if available_tokens >= normalized_cost:
                remaining = available_tokens - normalized_cost
                self._buckets.set(
                    bucket_id,
                    _TokenBucketState(tokens=remaining, updated_at_monotonic=updated_at),
                )
                return RateLimitDecision(
                    allowed=True,
                    retry_after_seconds=0,
                    tokens_remaining=remaining,
                )
            shortfall = normalized_cost - available_tokens
            if normalized_rule.refill_tokens_per_second <= 0.0:
                retry_after = 1
            else:
                retry_after = max(1, int(math.ceil(shortfall / normalized_rule.refill_tokens_per_second)))
            self._buckets.set(
                bucket_id,
                _TokenBucketState(tokens=available_tokens, updated_at_monotonic=updated_at),
            )
            return RateLimitDecision(
                allowed=False,
                retry_after_seconds=retry_after,
                tokens_remaining=available_tokens,
            )
