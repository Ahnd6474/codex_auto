from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
import time
from typing import Any, Callable


@dataclass(slots=True)
class _SnapshotCacheEntry:
    checked_at_monotonic: float
    snapshot: Any


@dataclass(slots=True)
class CodexBackendSnapshotService:
    fetcher: Callable[[str], Any]
    ttl_seconds: float = 10.0
    _entries: dict[str, _SnapshotCacheEntry] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def get_snapshot(self, codex_path: str = "codex.cmd", *, force_refresh: bool = False) -> Any:
        cache_key = str(codex_path or "codex.cmd").strip() or "codex.cmd"
        now = time.monotonic()
        with self._lock:
            cached = self._entries.get(cache_key)
            if (
                not force_refresh
                and cached is not None
                and (now - cached.checked_at_monotonic) <= max(0.0, float(self.ttl_seconds))
            ):
                return cached.snapshot
        snapshot = self.fetcher(cache_key)
        with self._lock:
            self._entries[cache_key] = _SnapshotCacheEntry(checked_at_monotonic=time.monotonic(), snapshot=snapshot)
        return snapshot

    def invalidate(self, codex_path: str = "codex.cmd") -> None:
        cache_key = str(codex_path or "codex.cmd").strip() or "codex.cmd"
        with self._lock:
            self._entries.pop(cache_key, None)
