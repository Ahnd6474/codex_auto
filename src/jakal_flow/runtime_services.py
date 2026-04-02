from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .lru_ttl_cache import LruTtlCache
from .platform_defaults import default_codex_path


@dataclass(slots=True)
class CodexBackendSnapshotService:
    fetcher: Callable[[str], Any]
    ttl_seconds: float = 10.0
    _cache: LruTtlCache[str, Any] = field(init=False)

    def __post_init__(self) -> None:
        self._cache = LruTtlCache(
            max_entries=16,
            ttl_seconds=self.ttl_seconds,
        )

    def peek_snapshot(self, codex_path: str = "") -> Any | None:
        cache_key = str(codex_path or "").strip() or default_codex_path()
        return self._cache.peek(cache_key)

    def get_snapshot(self, codex_path: str = "", *, force_refresh: bool = False) -> Any:
        cache_key = str(codex_path or "").strip() or default_codex_path()
        if not force_refresh:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached
        snapshot = self.fetcher(cache_key)
        self._cache.set(cache_key, snapshot, ttl_seconds=self.ttl_seconds)
        return snapshot

    def invalidate(self, codex_path: str = "") -> None:
        cache_key = str(codex_path or "").strip() or default_codex_path()
        self._cache.pop(cache_key)
