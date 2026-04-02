from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jakal_flow.lru_ttl_cache import LruTtlCache
from jakal_flow.rate_limiter import TokenBucketRateLimiter, TokenBucketRule


class LruTtlCacheTests(unittest.TestCase):
    def test_cache_evicts_least_recently_used_entry(self) -> None:
        current_time = {"value": 0.0}

        def fake_monotonic() -> float:
            return current_time["value"]

        with mock.patch("jakal_flow.lru_ttl_cache.time.monotonic", side_effect=fake_monotonic):
            cache = LruTtlCache[str, int](max_entries=2, ttl_seconds=30.0)
            cache.set("a", 1)
            cache.set("b", 2)
            self.assertEqual(cache.get("a"), 1)
            cache.set("c", 3)

            self.assertEqual(cache.get("a"), 1)
            self.assertIsNone(cache.get("b"))
            self.assertEqual(cache.get("c"), 3)

    def test_cache_expires_entries_after_ttl(self) -> None:
        current_time = {"value": 0.0}

        def fake_monotonic() -> float:
            return current_time["value"]

        with mock.patch("jakal_flow.lru_ttl_cache.time.monotonic", side_effect=fake_monotonic):
            cache = LruTtlCache[str, str](max_entries=2, ttl_seconds=5.0)
            cache.set("session", "active")

            current_time["value"] = 4.0
            self.assertEqual(cache.get("session"), "active")

            current_time["value"] = 5.1
            self.assertIsNone(cache.get("session"))


class TokenBucketRateLimiterTests(unittest.TestCase):
    def test_token_bucket_blocks_until_tokens_refill(self) -> None:
        limiter = TokenBucketRateLimiter(max_buckets=8, bucket_ttl_seconds=60.0)
        rule = TokenBucketRule(capacity=2.0, refill_tokens_per_second=1.0)

        first = limiter.consume("client-1", rule=rule, now_monotonic=0.0)
        second = limiter.consume("client-1", rule=rule, now_monotonic=0.0)
        blocked = limiter.consume("client-1", rule=rule, now_monotonic=0.0)
        recovered = limiter.consume("client-1", rule=rule, now_monotonic=1.0)

        self.assertTrue(first.allowed)
        self.assertTrue(second.allowed)
        self.assertFalse(blocked.allowed)
        self.assertEqual(blocked.retry_after_seconds, 1)
        self.assertTrue(recovered.allowed)


if __name__ == "__main__":
    unittest.main()
