from __future__ import annotations

from dataclasses import dataclass
import ctypes
import os
from typing import Any


DEFAULT_MEMORY_BUDGET_PER_WORKER_BYTES = 3 * 1024 * 1024 * 1024


@dataclass(slots=True)
class ParallelResourcePlan:
    worker_mode: str
    requested_workers: int
    cpu_logical_count: int
    cpu_parallel_limit: int
    memory_total_bytes: int | None
    memory_available_bytes: int | None
    memory_parallel_limit: int | None
    recommended_workers: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker_mode": self.worker_mode,
            "requested_workers": self.requested_workers,
            "cpu_logical_count": self.cpu_logical_count,
            "cpu_parallel_limit": self.cpu_parallel_limit,
            "memory_total_bytes": self.memory_total_bytes,
            "memory_available_bytes": self.memory_available_bytes,
            "memory_parallel_limit": self.memory_parallel_limit,
            "recommended_workers": self.recommended_workers,
            "reason": self.reason,
        }


def normalize_parallel_worker_mode(value: str | None) -> str:
    return "manual" if str(value or "").strip().lower() == "manual" else "auto"


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return parsed


def _detect_memory_bytes() -> tuple[int | None, int | None]:
    if os.name == "nt":
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.ullTotalPhys), int(status.ullAvailPhys)
        return None, None

    try:
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        total_pages = int(os.sysconf("SC_PHYS_PAGES"))
        available_pages = int(os.sysconf("SC_AVPHYS_PAGES"))
    except (AttributeError, OSError, TypeError, ValueError):
        return None, None
    return page_size * total_pages, page_size * available_pages


def build_parallel_resource_plan(
    worker_mode: str | None,
    requested_workers: Any,
) -> ParallelResourcePlan:
    normalized_mode = normalize_parallel_worker_mode(worker_mode)
    cpu_logical_count = max(1, int(os.cpu_count() or 1))
    cpu_parallel_limit = max(1, cpu_logical_count // 4)
    memory_total_bytes, memory_available_bytes = _detect_memory_bytes()
    memory_parallel_limit: int | None = None
    if memory_available_bytes is not None and memory_available_bytes > 0:
        memory_parallel_limit = max(1, memory_available_bytes // DEFAULT_MEMORY_BUDGET_PER_WORKER_BYTES)

    hard_limit = cpu_parallel_limit
    if memory_parallel_limit is not None:
        hard_limit = max(1, min(hard_limit, memory_parallel_limit))

    requested = _positive_int(requested_workers, 0 if normalized_mode == "auto" else 1)
    if normalized_mode == "manual":
        requested = max(1, requested or 1)
        recommended = min(requested, hard_limit)
        reason = f"manual request capped by available compute resources (cpu/4 and memory budget)"
    else:
        requested = max(0, requested)
        recommended = hard_limit if requested <= 0 else min(requested, hard_limit)
        reason = "automatic worker count derived from available compute resources (cpu/4 and memory budget)"

    return ParallelResourcePlan(
        worker_mode=normalized_mode,
        requested_workers=requested,
        cpu_logical_count=cpu_logical_count,
        cpu_parallel_limit=cpu_parallel_limit,
        memory_total_bytes=memory_total_bytes,
        memory_available_bytes=memory_available_bytes,
        memory_parallel_limit=memory_parallel_limit,
        recommended_workers=max(1, recommended),
        reason=reason,
    )
