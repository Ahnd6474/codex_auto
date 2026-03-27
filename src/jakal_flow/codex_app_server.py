from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .model_constants import AUTO_MODEL_SLUG, VALID_REASONING_EFFORTS
from .model_providers import discover_local_model_catalog
from .platform_defaults import default_codex_path
from .utils import now_utc_iso

UTC = getattr(datetime, "UTC", timezone.utc)


APP_SERVER_TIMEOUT_SECS = 8.0
MODEL_PAGE_LIMIT = 100


def resolve_codex_path(codex_path: str) -> str:
    codex_path = str(codex_path or "").strip() or default_codex_path()
    if codex_path.lower() == "codex.cmd":
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidate = Path(appdata) / "npm" / "codex.cmd"
            if candidate.exists():
                return str(candidate)
    return codex_path


def is_auto_model(model: str) -> bool:
    return not str(model or "").strip() or str(model).strip().lower() == AUTO_MODEL_SLUG


@dataclass(slots=True)
class CodexBackendSnapshot:
    checked_at: str
    available: bool
    model_catalog: list[dict[str, Any]] = field(default_factory=list)
    account: dict[str, Any] = field(default_factory=dict)
    rate_limits: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked_at": self.checked_at,
            "available": self.available,
            "model_catalog": self.model_catalog,
            "account": self.account,
            "rate_limits": self.rate_limits,
            "error": self.error,
        }


class _CodexAppServerSession:
    def __init__(self, codex_path: str) -> None:
        self.codex_path = resolve_codex_path(codex_path)
        self._next_id = 0
        self._stdout_queue: queue.Queue[str | None] = queue.Queue()
        self._stderr_queue: queue.Queue[str | None] = queue.Queue()
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self.process: subprocess.Popen[str] | None = None

    def __enter__(self) -> "_CodexAppServerSession":
        self.process = subprocess.Popen(
            [self.codex_path, "app-server", "--listen", "stdio://"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        assert self.process.stdout is not None
        assert self.process.stderr is not None
        self._stdout_thread = threading.Thread(
            target=self._pump_stream,
            args=(self.process.stdout, self._stdout_queue),
            daemon=True,
        )
        self._stderr_thread = threading.Thread(
            target=self._pump_stream,
            args=(self.process.stderr, self._stderr_queue),
            daemon=True,
        )
        self._stdout_thread.start()
        self._stderr_thread.start()
        self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "jakal-flow",
                    "version": "0.1.0",
                }
            },
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.process is None:
            return
        try:
            self.process.terminate()
            self.process.wait(timeout=1.5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=1.5)
        except OSError:
            pass

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.process is None or self.process.stdin is None:
            raise RuntimeError("Codex app-server is not running.")
        self._next_id += 1
        request_id = self._next_id
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }
        self.process.stdin.write(json.dumps(payload, ensure_ascii=False))
        self.process.stdin.write("\n")
        self.process.stdin.flush()
        return self._read_response(request_id)

    def _read_response(self, request_id: int) -> dict[str, Any]:
        while True:
            try:
                line = self._stdout_queue.get(timeout=APP_SERVER_TIMEOUT_SECS)
            except queue.Empty as exc:
                raise RuntimeError(
                    f"Timed out waiting for Codex app-server response to {request_id}. stderr={self._read_stderr_excerpt()}"
                ) from exc
            if line is None:
                raise RuntimeError(f"Codex app-server closed unexpectedly. stderr={self._read_stderr_excerpt()}")
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            if payload.get("id") != request_id:
                continue
            if "error" in payload:
                raise RuntimeError(f"Codex app-server request failed: {payload['error']}")
            result = payload.get("result", {})
            return result if isinstance(result, dict) else {}

    def _read_stderr_excerpt(self, limit: int = 6) -> str:
        lines: list[str] = []
        while len(lines) < limit:
            try:
                line = self._stderr_queue.get_nowait()
            except queue.Empty:
                break
            if line is None:
                break
            stripped = line.strip()
            if stripped:
                lines.append(stripped)
        return " | ".join(lines)

    @staticmethod
    def _pump_stream(stream, sink: queue.Queue[str | None]) -> None:
        try:
            for line in stream:
                sink.put(line)
        finally:
            sink.put(None)


def fetch_codex_backend_snapshot(codex_path: str = "") -> CodexBackendSnapshot:
    checked_at = now_utc_iso()
    try:
        with _CodexAppServerSession(codex_path) as session:
            account_result = session.request("account/read", {"refreshToken": False})
            rate_limit_result = session.request("account/rateLimits/read", {})
            model_catalog = _merge_model_catalogs(_read_model_catalog(session), discover_local_model_catalog())
        return CodexBackendSnapshot(
            checked_at=checked_at,
            available=True,
            model_catalog=model_catalog,
            account=_format_account_snapshot(account_result),
            rate_limits=_format_rate_limits(rate_limit_result),
        )
    except Exception as exc:
        local_models = discover_local_model_catalog()
        return CodexBackendSnapshot(
            checked_at=checked_at,
            available=bool(local_models),
            model_catalog=_merge_model_catalogs([_auto_model_entry()], local_models),
            account={
                "authenticated": False,
                "requires_openai_auth": True,
                "type": "",
                "email": "",
                "plan_type": "unknown",
            },
            rate_limits={"default_limit_id": "", "items": []},
            error=str(exc),
        )


def _read_model_catalog(session: _CodexAppServerSession) -> list[dict[str, Any]]:
    models = [_auto_model_entry()]
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {
            "includeHidden": True,
            "limit": MODEL_PAGE_LIMIT,
        }
        if cursor:
            params["cursor"] = cursor
        result = session.request("model/list", params)
        raw_items = result.get("data", [])
        if isinstance(raw_items, list):
            for item in raw_items:
                if isinstance(item, dict):
                    models.append(_format_model_entry(item))
        next_cursor = result.get("nextCursor")
        cursor = str(next_cursor).strip() if isinstance(next_cursor, str) and next_cursor.strip() else None
        if not cursor:
            break
    return models


def _auto_model_entry() -> dict[str, Any]:
    return {
        "id": AUTO_MODEL_SLUG,
        "model": AUTO_MODEL_SLUG,
        "display_name": "Auto",
        "description": "Use Codex default model routing from the installed CLI.",
        "hidden": False,
        "is_default": True,
        "default_reasoning_effort": "medium",
        "supported_reasoning_efforts": ["low", "medium", "high", "xhigh"],
        "input_modalities": ["text", "image"],
        "supports_personality": True,
        "upgrade": None,
        "availability_nux": None,
        "provider": "openai",
        "local_provider": None,
    }


def _format_model_entry(item: dict[str, Any]) -> dict[str, Any]:
    supported: list[str] = []
    for option in item.get("supportedReasoningEfforts", []):
        if not isinstance(option, dict):
            continue
        effort = str(option.get("reasoningEffort", "")).strip().lower()
        if effort in VALID_REASONING_EFFORTS and effort not in supported:
            supported.append(effort)
    default_effort = str(item.get("defaultReasoningEffort", "")).strip().lower()
    if default_effort not in VALID_REASONING_EFFORTS:
        default_effort = supported[0] if supported else "medium"
    if not supported:
        supported = [default_effort]
    availability = item.get("availabilityNux")
    return {
        "id": str(item.get("id", item.get("model", ""))).strip(),
        "model": str(item.get("model", "")).strip(),
        "display_name": str(item.get("displayName", item.get("model", ""))).strip(),
        "description": str(item.get("description", "")).strip(),
        "hidden": bool(item.get("hidden", False)),
        "is_default": bool(item.get("isDefault", False)),
        "default_reasoning_effort": default_effort,
        "supported_reasoning_efforts": supported,
        "input_modalities": [str(value).strip() for value in item.get("inputModalities", []) if str(value).strip()],
        "supports_personality": bool(item.get("supportsPersonality", False)),
        "upgrade": str(item.get("upgrade", "")).strip() or None,
        "availability_nux": availability if isinstance(availability, dict) else None,
        "provider": "openai",
        "local_provider": None,
    }


def _merge_model_catalogs(*catalogs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for catalog in catalogs:
        for item in catalog:
            if not isinstance(item, dict):
                continue
            provider = str(item.get("provider", "openai")).strip().lower() or "openai"
            local_provider = str(item.get("local_provider", "")).strip().lower()
            model = str(item.get("model", "")).strip().lower()
            if not model:
                continue
            key = (provider, local_provider, model)
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def _format_account_snapshot(result: dict[str, Any]) -> dict[str, Any]:
    account = result.get("account")
    if not isinstance(account, dict):
        account = {}
    return {
        "authenticated": bool(account),
        "requires_openai_auth": bool(result.get("requiresOpenaiAuth", True)),
        "type": str(account.get("type", "")).strip(),
        "email": str(account.get("email", "")).strip(),
        "plan_type": str(account.get("planType", "unknown")).strip() or "unknown",
    }


def _format_rate_limits(result: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    default_limit_id = ""
    by_limit_id = result.get("rateLimitsByLimitId")
    if isinstance(by_limit_id, dict) and by_limit_id:
        for limit_id, raw in by_limit_id.items():
            if isinstance(raw, dict):
                formatted = _format_rate_limit_snapshot(raw)
                if not formatted["limit_id"]:
                    formatted["limit_id"] = str(limit_id).strip()
                items.append(formatted)
    else:
        fallback = result.get("rateLimits")
        if isinstance(fallback, dict):
            items.append(_format_rate_limit_snapshot(fallback))
    if items:
        default_limit_id = items[0]["limit_id"]
    items.sort(key=lambda item: (item["limit_id"] != "codex", item["limit_id"]))
    return {
        "default_limit_id": default_limit_id,
        "items": items,
    }


def _format_rate_limit_snapshot(raw: dict[str, Any]) -> dict[str, Any]:
    credits = raw.get("credits")
    formatted_credits = None
    if isinstance(credits, dict):
        formatted_credits = {
            "has_credits": bool(credits.get("hasCredits", False)),
            "unlimited": bool(credits.get("unlimited", False)),
            "balance": str(credits.get("balance", "")).strip() or None,
        }
    return {
        "limit_id": str(raw.get("limitId", "")).strip(),
        "limit_name": str(raw.get("limitName", "")).strip() or None,
        "plan_type": str(raw.get("planType", "unknown")).strip() or "unknown",
        "primary": _format_rate_limit_window(raw.get("primary")),
        "secondary": _format_rate_limit_window(raw.get("secondary")),
        "credits": formatted_credits,
    }


def _format_rate_limit_window(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    used_percent = _coerce_int(raw.get("usedPercent"))
    resets_at_unix = _coerce_int(raw.get("resetsAt"), allow_zero=True)
    window_duration = _coerce_int(raw.get("windowDurationMins"), allow_zero=True)
    return {
        "used_percent": used_percent,
        "remaining_percent": max(0, 100 - used_percent),
        "window_duration_mins": window_duration if window_duration > 0 else None,
        "resets_at_unix": resets_at_unix if resets_at_unix > 0 else None,
        "resets_at": _format_unix_timestamp(resets_at_unix),
    }


def _coerce_int(value: Any, allow_zero: bool = False) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    if parsed < 0:
        return 0
    if parsed == 0 and not allow_zero:
        return 0
    return parsed


def _format_unix_timestamp(value: int) -> str | None:
    if value <= 0:
        return None
    return datetime.fromtimestamp(value, tz=UTC).replace(microsecond=0).isoformat()
