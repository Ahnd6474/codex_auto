from __future__ import annotations

from typing import Any

from .models import ProjectContext
from .utils import now_utc_iso, read_json, write_json


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def normalize_run_control(payload: Any) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    return {
        "stop_after_current_step": _coerce_bool(data.get("stop_after_current_step", False), False),
        "stop_immediately": _coerce_bool(data.get("stop_immediately", False), False),
        "requested_at": _optional_text(data.get("requested_at")),
        "request_source": _optional_text(data.get("request_source")),
    }


def default_run_control() -> dict[str, Any]:
    return {
        "stop_after_current_step": False,
        "stop_immediately": False,
        "requested_at": None,
        "request_source": None,
    }


def load_run_control(context: ProjectContext) -> dict[str, Any]:
    return normalize_run_control(read_json(context.paths.ui_control_file, default=None))


def save_run_control(context: ProjectContext, payload: dict[str, Any]) -> dict[str, Any]:
    state = normalize_run_control(payload)
    write_json(context.paths.ui_control_file, state)
    return state


def clear_stop_request(context: ProjectContext) -> dict[str, Any]:
    return save_run_control(context, default_run_control())


def request_stop_after_current_step(context: ProjectContext, request_source: str = "desktop-ui") -> dict[str, Any]:
    return save_run_control(
        context,
        {
            "stop_after_current_step": True,
            "stop_immediately": False,
            "requested_at": now_utc_iso(),
            "request_source": request_source,
        },
    )


def request_stop_immediately(context: ProjectContext, request_source: str = "desktop-ui") -> dict[str, Any]:
    return save_run_control(
        context,
        {
            "stop_after_current_step": False,
            "stop_immediately": True,
            "requested_at": now_utc_iso(),
            "request_source": request_source,
        },
    )


def stop_requested(context: ProjectContext) -> bool:
    return bool(load_run_control(context).get("stop_after_current_step"))


def immediate_stop_requested(context: ProjectContext) -> bool:
    return bool(load_run_control(context).get("stop_immediately"))
