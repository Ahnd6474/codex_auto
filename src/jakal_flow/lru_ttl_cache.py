from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
import time
from typing import Callable, Generic, TypeVar


K = TypeVar("K")
V = TypeVar("V")


@dataclass(slots=True)
class _CacheEntry(Generic[V]):
    value: V
    expires_at_monotonic: float | None


class LruTtlCache(Generic[K, V]):
    def __init__(self, *, max_entries: int, ttl_seconds: float | None = None) -> None:
        self._max_entries = max(1, int(max_entries))
        self._ttl_seconds = ttl_seconds if ttl_seconds is None else max(0.0, float(ttl_seconds))
        self._entries: OrderedDict[K, _CacheEntry[V]] = OrderedDict()
        self._lock = Lock()

    def get(self, key: K) -> V | None:
        now = time.monotonic()
        with self._lock:
            self._purge_expired_unlocked(now)
            entry = self._entries.get(key)
            if entry is None:
                return None
            if self._is_expired(entry, now):
                self._entries.pop(key, None)
                return None
            self._entries.move_to_end(key)
            return entry.value

    def peek(self, key: K) -> V | None:
        now = time.monotonic()
        with self._lock:
            self._purge_expired_unlocked(now)
            entry = self._entries.get(key)
            if entry is None:
                return None
            if self._is_expired(entry, now):
                self._entries.pop(key, None)
                return None
            return entry.value

    def set(self, key: K, value: V, *, ttl_seconds: float | None = None) -> None:
        now = time.monotonic()
        effective_ttl = self._ttl_seconds if ttl_seconds is None else max(0.0, float(ttl_seconds))
        expires_at = None if effective_ttl is None else now + effective_ttl
        with self._lock:
            self._purge_expired_unlocked(now)
            self._entries.pop(key, None)
            self._entries[key] = _CacheEntry(value=value, expires_at_monotonic=expires_at)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def pop(self, key: K) -> V | None:
        with self._lock:
            entry = self._entries.pop(key, None)
            return None if entry is None else entry.value

    def remove_if(self, predicate: Callable[[K], bool]) -> int:
        now = time.monotonic()
        with self._lock:
            self._purge_expired_unlocked(now)
            removed = 0
            for key in list(self._entries.keys()):
                if not predicate(key):
                    continue
                self._entries.pop(key, None)
                removed += 1
            return removed

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        now = time.monotonic()
        with self._lock:
            self._purge_expired_unlocked(now)
            return len(self._entries)

    @staticmethod
    def _is_expired(entry: _CacheEntry[V], now: float) -> bool:
        return entry.expires_at_monotonic is not None and now >= entry.expires_at_monotonic

    def _purge_expired_unlocked(self, now: float) -> None:
        stale_keys = [
            key
            for key, entry in self._entries.items()
            if self._is_expired(entry, now)
        ]
        for key in stale_keys:
            self._entries.pop(key, None)
