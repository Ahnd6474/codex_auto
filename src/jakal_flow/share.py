from __future__ import annotations

import hmac
import os
import re
import secrets
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .models import ExecutionPlanState, ProjectContext
from .planning import execution_plan_svg
from .run_control import load_run_control
from .status_views import effective_project_status
from .utils import (
    append_jsonl,
    compact_text,
    decode_process_output,
    now_utc_iso,
    read_json,
    read_jsonl_tail,
    read_last_jsonl,
    write_json,
)
from .workspace import WorkspaceManager

UTC = getattr(datetime, "UTC", timezone.utc)


DEFAULT_SHARE_HOST = "0.0.0.0"
DEFAULT_SHARE_PORT = 0
DEFAULT_SHARE_TTL_MINUTES = 60
MAX_PUBLIC_LOG_LINE_CHARS = 240
MAX_PUBLIC_LOG_LINES = 12
DEFAULT_VIEWER_PATH = "/share/view"
DEFAULT_SHARE_PUBLIC_BASE_URL = ""
_UNSET = object()

TOKEN_PATTERNS = [
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b(?:eyJ[A-Za-z0-9_-]{8,}\.){2}[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
]
SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)\b("
    r"authorization|token|secret|password|passwd|pwd|api[_-]?key|access[_-]?key|refresh[_-]?token|client[_-]?secret"
    r")\b\s*([:=])\s*([^\s,;]+)"
)
WINDOWS_PATH_RE = re.compile(r"\b[A-Za-z]:\\(?:[^\\\s]+\\)*[^\\\s]*")
UNIX_PATH_RE = re.compile(r"(?<!https:)(?<!http:)(?<![A-Za-z0-9._-])/(?:[^/\s]+/)+[^/\s]*")
URL_CREDENTIAL_RE = re.compile(r"(?i)\b(https?://)([^/\s:@]+):([^@\s]+)@")
WHITESPACE_RE = re.compile(r"\s+")


def _normalize(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    return value


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def normalize_share_bind_host(value: str) -> str:
    text = str(value or "").strip()
    if not text or text == "127.0.0.1":
        return DEFAULT_SHARE_HOST
    return text


def iso_after_minutes(minutes: int) -> str:
    safe_minutes = max(1, int(minutes))
    return (datetime.now(tz=UTC) + timedelta(minutes=safe_minutes)).replace(microsecond=0).isoformat()


def share_sessions_file(context: ProjectContext) -> Path:
    return context.paths.state_dir / "share_sessions.json"


def workspace_share_sessions_file(workspace_root: Path) -> Path:
    return workspace_root / "share_sessions.json"


def share_server_status_file(workspace_root: Path) -> Path:
    return workspace_root / "share_server.json"


def share_server_log_file(workspace_root: Path) -> Path:
    return workspace_root / "share_server.log"


def share_server_config_file(workspace_root: Path) -> Path:
    return workspace_root / "share_server_config.json"


def share_audit_log_file(workspace_root: Path) -> Path:
    return workspace_root / "share_session_events.jsonl"


@dataclass(slots=True)
class ShareSession:
    session_id: str
    viewer_token: str
    created_at: str
    expires_at: str
    revoked_at: str | None = None
    created_by: str = "desktop-ui"

    def to_dict(self) -> dict[str, Any]:
        return _normalize(asdict(self))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ShareSession":
        revoked_raw = data.get("revoked_at")
        return cls(
            session_id=str(data.get("session_id", "")).strip(),
            viewer_token=str(data.get("viewer_token", "")).strip(),
            created_at=str(data.get("created_at", "")).strip(),
            expires_at=str(data.get("expires_at", "")).strip(),
            revoked_at=revoked_raw.strip() if isinstance(revoked_raw, str) and revoked_raw.strip() else None,
            created_by=str(data.get("created_by", "desktop-ui")).strip() or "desktop-ui",
        )

    def is_revoked(self) -> bool:
        return bool(self.revoked_at)

    def is_expired(self, now: datetime | None = None) -> bool:
        expiry = parse_iso_datetime(self.expires_at)
        if expiry is None:
            return True
        return expiry <= (now or datetime.now(tz=UTC))

    def is_active(self, now: datetime | None = None) -> bool:
        return not self.is_revoked() and not self.is_expired(now=now)


@dataclass(slots=True)
class ShareServerState:
    host: str
    port: int
    pid: int
    started_at: str
    viewer_path: str = DEFAULT_VIEWER_PATH

    def to_dict(self) -> dict[str, Any]:
        return _normalize(asdict(self))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ShareServerState":
        return cls(
            host=str(data.get("host", DEFAULT_SHARE_HOST)).strip() or DEFAULT_SHARE_HOST,
            port=int(data.get("port", DEFAULT_SHARE_PORT)),
            pid=int(data.get("pid", 0)),
            started_at=str(data.get("started_at", "")).strip(),
            viewer_path=str(data.get("viewer_path", DEFAULT_VIEWER_PATH)).strip() or DEFAULT_VIEWER_PATH,
        )

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


@dataclass(slots=True)
class ShareServerConfig:
    bind_host: str = DEFAULT_SHARE_HOST
    preferred_port: int = DEFAULT_SHARE_PORT
    public_base_url: str = DEFAULT_SHARE_PUBLIC_BASE_URL
    access_token: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _normalize(asdict(self))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ShareServerConfig":
        preferred_port_raw = data.get("preferred_port", DEFAULT_SHARE_PORT)
        try:
            preferred_port = max(0, int(preferred_port_raw))
        except (TypeError, ValueError):
            preferred_port = DEFAULT_SHARE_PORT
        return cls(
            bind_host=normalize_share_bind_host(str(data.get("bind_host", DEFAULT_SHARE_HOST)).strip()),
            preferred_port=preferred_port,
            public_base_url=normalize_public_base_url(str(data.get("public_base_url", DEFAULT_SHARE_PUBLIC_BASE_URL)).strip()),
            access_token=str(data.get("access_token", "")).strip(),
        )


def normalize_public_base_url(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.rstrip("/")


def process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        completed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            check=False,
            capture_output=True,
        )
        stdout = decode_process_output(completed.stdout)
        return f"{pid}" in stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    stat_path = Path("/proc") / str(pid) / "stat"
    if stat_path.exists():
        try:
            fields = stat_path.read_text(encoding="utf-8").split()
            if len(fields) >= 3 and fields[2] == "Z":
                return False
        except OSError:
            pass
    return True


def load_share_server_state(workspace_root: Path) -> ShareServerState | None:
    raw = read_json(share_server_status_file(workspace_root), default=None)
    if not isinstance(raw, dict):
        return None
    try:
        return ShareServerState.from_dict(raw)
    except (TypeError, ValueError):
        return None


def clear_share_server_state(workspace_root: Path) -> None:
    try:
        share_server_status_file(workspace_root).unlink(missing_ok=True)
    except OSError:
        pass


def load_share_server_config(workspace_root: Path) -> ShareServerConfig:
    raw = read_json(share_server_config_file(workspace_root), default={})
    if not isinstance(raw, dict):
        return ShareServerConfig()
    try:
        return ShareServerConfig.from_dict(raw)
    except (TypeError, ValueError):
        return ShareServerConfig()


def save_share_server_config(workspace_root: Path, config: ShareServerConfig) -> ShareServerConfig:
    normalized = ShareServerConfig.from_dict(config.to_dict())
    write_json(share_server_config_file(workspace_root), normalized.to_dict())
    return normalized


def ensure_share_access_token(workspace_root: Path, config: ShareServerConfig | None = None) -> str:
    current = config or load_share_server_config(workspace_root)
    access_token = str(getattr(current, "access_token", "") or "").strip()
    if access_token:
        return access_token
    current.access_token = secrets.token_urlsafe(24)
    save_share_server_config(workspace_root, current)
    return current.access_token


def share_server_status_payload(workspace_root: Path) -> dict[str, Any]:
    from .public_tunnel import normalize_tunnel_target_url, public_tunnel_status_payload

    config = load_share_server_config(workspace_root)
    tunnel = public_tunnel_status_payload(workspace_root)
    state = load_share_server_state(workspace_root)
    tunnel_public_url = str(tunnel.get("public_url") or "").strip()
    tunnel_target = normalize_tunnel_target_url(str(tunnel.get("target_url") or "").strip())
    if state is None:
        return {
            "running": False,
            "host": DEFAULT_SHARE_HOST,
            "port": None,
            "base_url": None,
            "viewer_path": DEFAULT_VIEWER_PATH,
            "config": config.to_dict(),
            "share_base_url": config.public_base_url or None,
            "share_base_url_source": "config" if config.public_base_url else None,
            "public_tunnel": tunnel,
        }
    running = process_is_running(state.pid)
    local_tunnel_target = normalize_tunnel_target_url(state.base_url if running else "")
    tunnel_matches_server = bool(
        running
        and bool(tunnel.get("running"))
        and tunnel_public_url
        and local_tunnel_target
        and tunnel_target == local_tunnel_target
    )
    share_base_url = config.public_base_url or (tunnel_public_url if tunnel_matches_server else "") or (state.base_url if running else None)
    share_base_url_source = (
        "config"
        if config.public_base_url
        else ("quick_tunnel" if tunnel_matches_server else ("local" if running else None))
    )
    if not running:
        clear_share_server_state(workspace_root)
    payload = {
        "running": running,
        "host": state.host,
        "port": state.port if running else None,
        "pid": state.pid if running else None,
        "started_at": state.started_at if running else None,
        "base_url": state.base_url if running else None,
        "viewer_path": state.viewer_path,
        "config": config.to_dict(),
        "share_base_url": share_base_url,
        "share_base_url_source": share_base_url_source,
        "public_tunnel": tunnel,
    }
    return payload


def _load_share_sessions_from_file(path: Path) -> list[ShareSession]:
    raw = read_json(path, default={"sessions": []})
    items = raw.get("sessions", []) if isinstance(raw, dict) else []
    sessions: list[ShareSession] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        session = ShareSession.from_dict(item)
        if session.session_id and session.viewer_token:
            sessions.append(session)
    return sessions


def _save_share_sessions_to_file(path: Path, sessions: list[ShareSession]) -> None:
    write_json(
        path,
        {"sessions": [session.to_dict() for session in sessions]},
    )


def load_share_sessions(context: ProjectContext) -> list[ShareSession]:
    return _load_share_sessions_from_file(share_sessions_file(context))


def save_share_sessions(context: ProjectContext, sessions: list[ShareSession]) -> None:
    _save_share_sessions_to_file(share_sessions_file(context), sessions)


def load_workspace_share_sessions(workspace_root: Path) -> list[ShareSession]:
    return _load_share_sessions_from_file(workspace_share_sessions_file(workspace_root))


def save_workspace_share_sessions(workspace_root: Path, sessions: list[ShareSession]) -> None:
    _save_share_sessions_to_file(workspace_share_sessions_file(workspace_root), sessions)


def append_share_audit_event(workspace_root: Path, event_type: str, details: dict[str, Any] | None = None) -> None:
    append_jsonl(
        share_audit_log_file(workspace_root),
        {
            "timestamp": now_utc_iso(),
            "event_type": str(event_type or "").strip() or "share-session-event",
            "details": _normalize(details or {}),
        },
    )


def create_share_session(
    context: ProjectContext,
    expires_in_minutes: int = DEFAULT_SHARE_TTL_MINUTES,
    created_by: str = "desktop-ui",
) -> ShareSession:
    session = ShareSession(
        session_id=secrets.token_hex(16),
        viewer_token=secrets.token_urlsafe(24),
        created_at=now_utc_iso(),
        expires_at=iso_after_minutes(expires_in_minutes),
        created_by=created_by,
    )
    sessions = load_share_sessions(context)
    for existing in sessions:
        if existing.is_active():
            existing.revoked_at = now_utc_iso()
    sessions.append(session)
    save_share_sessions(context, sessions)
    return session


def iter_workspace_share_sessions(workspace_root: Path) -> list[tuple[ProjectContext, ShareSession]]:
    manager = WorkspaceManager(workspace_root)
    items: list[tuple[ProjectContext, ShareSession]] = []
    for project in manager.list_projects():
        for session in load_share_sessions(project):
            items.append((project, session))
    return items


def revoke_workspace_active_share_sessions(workspace_root: Path) -> list[ShareSession]:
    revoked: list[ShareSession] = []
    for project, session in iter_workspace_share_sessions(workspace_root):
        if not session.is_active():
            continue
        session.revoked_at = now_utc_iso()
        sessions = load_share_sessions(project)
        changed = False
        for candidate in sessions:
            if candidate.session_id == session.session_id and candidate.is_active():
                candidate.revoked_at = session.revoked_at
                changed = True
        if changed:
            save_share_sessions(project, sessions)
            revoked.append(session)
    return revoked


def create_workspace_share_session(
    workspace_root: Path,
    context: ProjectContext | None = None,
    expires_in_minutes: int = DEFAULT_SHARE_TTL_MINUTES,
    created_by: str = "desktop-ui",
) -> ShareSession:
    legacy_revoked_sessions = revoke_workspace_active_share_sessions(workspace_root)
    sessions = load_workspace_share_sessions(workspace_root)
    revoked_session_ids: list[str] = []
    for existing in sessions:
        if existing.is_active():
            existing.revoked_at = now_utc_iso()
            revoked_session_ids.append(existing.session_id)
    session = ShareSession(
        session_id=secrets.token_hex(16),
        viewer_token=secrets.token_urlsafe(24),
        created_at=now_utc_iso(),
        expires_at=iso_after_minutes(expires_in_minutes),
        created_by=created_by,
    )
    sessions.append(session)
    save_workspace_share_sessions(workspace_root, sessions)
    append_share_audit_event(
        workspace_root,
        "share-session-created",
        {
            "session_id": session.session_id,
            "created_by": session.created_by,
            "expires_at": session.expires_at,
            "revoked_session_ids": revoked_session_ids + [item.session_id for item in legacy_revoked_sessions],
            "project": (
                {
                    "repo_id": context.metadata.repo_id,
                    "display_name": context.metadata.display_name or context.metadata.slug,
                    "project_dir": str(context.metadata.repo_path),
                }
                if context is not None
                else None
            ),
        },
    )
    return session


def _session_sort_key(session: ShareSession) -> tuple[datetime, str]:
    created_at = parse_iso_datetime(session.created_at) or datetime.min.replace(tzinfo=UTC)
    return created_at, session.session_id


def resolve_workspace_active_share_session(workspace_root: Path) -> tuple[ProjectContext | None, ShareSession] | None:
    active_sessions = [session for session in load_workspace_share_sessions(workspace_root) if session.is_active()]
    if active_sessions:
        return None, max(active_sessions, key=_session_sort_key)

    legacy_active_sessions = [
        (project, session)
        for project, session in iter_workspace_share_sessions(workspace_root)
        if session.is_active()
    ]
    if not legacy_active_sessions:
        return None
    return max(legacy_active_sessions, key=lambda item: _session_sort_key(item[1]))


def revoke_workspace_share_session(workspace_root: Path, session_id: str) -> ShareSession:
    target = session_id.strip()
    if not target:
        raise ValueError("session_id is required.")
    sessions = load_workspace_share_sessions(workspace_root)
    for session in sessions:
        if session.session_id == target:
            session.revoked_at = now_utc_iso()
            save_workspace_share_sessions(workspace_root, sessions)
            append_share_audit_event(
                workspace_root,
                "share-session-revoked",
                {
                    "session_id": session.session_id,
                    "revoked_at": session.revoked_at,
                },
            )
            return session
    raise KeyError(f"Unknown share session: {target}")


def find_workspace_share_session(workspace_root: Path, session_id: str) -> ShareSession | None:
    target = session_id.strip()
    if not target:
        return None
    for session in load_workspace_share_sessions(workspace_root):
        if session.session_id == target:
            return session
    return None


def create_legacy_workspace_share_session(
    workspace_root: Path,
    context: ProjectContext,
    expires_in_minutes: int = DEFAULT_SHARE_TTL_MINUTES,
    created_by: str = "desktop-ui",
) -> ShareSession:
    revoke_workspace_active_share_sessions(workspace_root)
    return create_share_session(
        context,
        expires_in_minutes=expires_in_minutes,
        created_by=created_by,
    )


def revoke_share_session(context: ProjectContext, session_id: str) -> ShareSession:
    target = session_id.strip()
    if not target:
        raise ValueError("session_id is required.")
    sessions = load_share_sessions(context)
    for session in sessions:
        if session.session_id == target:
            session.revoked_at = now_utc_iso()
            save_share_sessions(context, sessions)
            return session
    raise KeyError(f"Unknown share session: {target}")


def find_share_session(context: ProjectContext, session_id: str) -> ShareSession | None:
    target = session_id.strip()
    if not target:
        return None
    for session in load_share_sessions(context):
        if session.session_id == target:
            return session
    return None


def validate_share_session(session: ShareSession, viewer_token: str) -> None:
    supplied = viewer_token.strip()
    if not supplied or not hmac.compare_digest(session.viewer_token, supplied):
        raise PermissionError("Invalid share token.")
    if session.is_revoked():
        raise PermissionError("This share session has been revoked.")
    if session.is_expired():
        raise PermissionError("This share session has expired.")


def resolve_shared_access(workspace_root: Path, access_token: str) -> tuple[ProjectContext | None, ShareSession]:
    supplied = str(access_token or "").strip()
    config = load_share_server_config(workspace_root)
    expected = str(getattr(config, "access_token", "") or "").strip()
    if not supplied or not expected or not hmac.compare_digest(expected, supplied):
        raise PermissionError("Invalid share access token.")
    resolved = resolve_workspace_active_share_session(workspace_root)
    if resolved is None:
        raise KeyError("Unknown share session.")
    _project, session = resolved
    if session.is_revoked():
        raise PermissionError("This share session has been revoked.")
    if session.is_expired():
        raise PermissionError("This share session has expired.")
    return resolved


def resolve_shared_session(workspace_root: Path, session_id: str) -> tuple[ProjectContext | None, ShareSession]:
    workspace_session = find_workspace_share_session(workspace_root, session_id)
    if workspace_session is not None:
        return None, workspace_session
    manager = WorkspaceManager(workspace_root)
    for project in manager.list_projects():
        session = find_share_session(project, session_id)
        if session is not None:
            return project, session
    raise KeyError(f"Unknown share session: {session_id}")


def _legacy_workspace_active_share_session(
    workspace_root: Path,
    *,
    server: dict[str, Any] | None = None,
    state: ShareServerState | None | object = _UNSET,
) -> dict[str, Any] | None:
    if state is _UNSET:
        state = load_share_server_state(workspace_root)
    if server is None:
        server = share_server_status_payload(workspace_root)
    active_sessions = [
        (project, session)
        for project, session in iter_workspace_share_sessions(workspace_root)
        if session.is_active()
    ]
    if not active_sessions:
        return None

    project, session = max(active_sessions, key=lambda item: _session_sort_key(item[1]))
    payload = public_session_summary(
        workspace_root,
        project,
        session,
        include_token=False,
        server=server,
        state=state,
    )
    payload["project"] = {
        "repo_id": project.metadata.repo_id,
        "display_name": project.metadata.display_name or project.metadata.slug,
        "slug": project.metadata.slug,
    }
    return payload


def workspace_active_share_session(
    workspace_root: Path,
    *,
    server: dict[str, Any] | None = None,
    state: ShareServerState | None | object = _UNSET,
) -> dict[str, Any] | None:
    if state is _UNSET:
        state = load_share_server_state(workspace_root)
    if server is None:
        server = share_server_status_payload(workspace_root)
    active_sessions = [session for session in load_workspace_share_sessions(workspace_root) if session.is_active()]
    if active_sessions:
        session = max(active_sessions, key=_session_sort_key)
        return public_session_summary(
            workspace_root,
            None,
            session,
            include_token=False,
            server=server,
            state=state,
        )
    return _legacy_workspace_active_share_session(
        workspace_root,
        server=server,
        state=state,
    )


def mask_public_text(value: str, max_chars: int = MAX_PUBLIC_LOG_LINE_CHARS) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""
    text = URL_CREDENTIAL_RE.sub(r"\1[masked]@", text)
    text = SENSITIVE_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}{match.group(2)} [masked]", text)
    for pattern in TOKEN_PATTERNS:
        text = pattern.sub("[masked]", text)
    text = WINDOWS_PATH_RE.sub("[path]", text)
    text = UNIX_PATH_RE.sub("[path]", text)
    text = WHITESPACE_RE.sub(" ", text).strip()
    return compact_text(text, max_chars=max_chars)


def public_test_result(context: ProjectContext) -> dict[str, Any] | None:
    latest = read_last_jsonl(context.paths.logs_dir / "test_runs.jsonl")
    if not isinstance(latest, dict):
        return None
    return {
        "label": mask_public_text(str(latest.get("label", "")).strip(), max_chars=80),
        "block_index": int(latest.get("block_index", 0) or 0),
        "status": "passed" if int(latest.get("returncode", 1) or 1) == 0 else "failed",
        "returncode": int(latest.get("returncode", 1) or 1),
        "summary": mask_public_text(str(latest.get("summary", "")).strip()),
    }


def project_monitor_lines(context: ProjectContext, plan_state: ExecutionPlanState, limit: int = MAX_PUBLIC_LOG_LINES) -> list[str]:
    lines: list[str] = []
    for event in reversed(read_jsonl_tail(context.paths.ui_event_log_file, max(limit * 3, 24))):
        timestamp = str(event.get("timestamp", "")).strip()
        event_type = str(event.get("event_type", "")).strip()
        message = str(event.get("message", "")).strip()
        details = event.get("details", {})
        step_id = ""
        if isinstance(details, dict):
            step_id = str(details.get("step_id", "")).strip()
        detail_suffix = f" [{step_id}]" if step_id else ""
        line = mask_public_text(f"{timestamp} | {event_type}{detail_suffix} | {message}")
        if line:
            lines.append(line)
        if len(lines) >= limit:
            return lines

    for block in reversed(read_jsonl_tail(context.paths.block_log_file, max(limit * 2, 12))):
        block_index = block.get("block_index", "?")
        status = str(block.get("status", "unknown")).strip()
        title = mask_public_text(str(block.get("selected_task", "")).strip(), max_chars=100)
        summary = mask_public_text(str(block.get("test_summary", "")).strip(), max_chars=100)
        lines.append(f"block {block_index} | {status} | {title} | {summary}".strip())
        if len(lines) >= limit:
            return lines

    if not lines:
        if plan_state.steps:
            lines.append(f"Plan loaded with {len(plan_state.steps)} step(s).")
        else:
            lines.append("No plan has been generated yet.")
    return lines[:limit]


def current_step_summary(plan_state: ExecutionPlanState) -> dict[str, Any] | None:
    active_steps = [step for step in plan_state.steps if step.status in {"running", "integrating"}]
    if len(active_steps) > 1:
        step_ids = ", ".join(step.step_id for step in active_steps)
        step_titles = ", ".join(step.title for step in active_steps if step.title)
        summary = step_titles or f"Parallel batch running: {step_ids}"
        return {
            "step_id": step_ids,
            "title": mask_public_text(f"Parallel batch: {step_ids}", max_chars=120),
            "summary": mask_public_text(summary, max_chars=180),
            "status": "running",
        }
    current = active_steps[0] if active_steps else None
    if current is None:
        current = next((step for step in plan_state.steps if step.status != "completed"), None)
    if current is None:
        return None
    return {
        "step_id": current.step_id,
        "title": mask_public_text(current.title, max_chars=120),
        "summary": mask_public_text(
            current.display_description or current.codex_description or current.notes,
            max_chars=180,
        ),
        "status": current.status,
    }


def last_updated_timestamp(context: ProjectContext, plan_state: ExecutionPlanState) -> str | None:
    candidates = [
        context.metadata.last_run_at,
        context.loop_state.last_block_completed_at,
        plan_state.last_updated_at,
    ]
    latest_event = read_last_jsonl(context.paths.ui_event_log_file)
    if isinstance(latest_event, dict):
        candidates.append(str(latest_event.get("timestamp", "")).strip() or None)
    latest_report = read_json(context.paths.reports_dir / "latest_report.json", default={})
    if isinstance(latest_report, dict):
        candidates.append(str(latest_report.get("generated_at", "")).strip() or None)
    parsed = [item for item in (parse_iso_datetime(value) for value in candidates) if item is not None]
    if not parsed:
        return None
    return max(parsed).replace(microsecond=0).isoformat()


def current_phase(context: ProjectContext, plan_state: ExecutionPlanState) -> str | None:
    status = effective_project_status(context.metadata.current_status, plan_state, context.loop_state)
    if not status:
        return None
    if status.startswith("running:block:"):
        block = status.rsplit(":", 1)[-1]
        return f"block {block}"
    if status == "running:closeout":
        return "closeout"
    if status.startswith("running:"):
        return status.split(":", 1)[1]
    if context.loop_state.block_index > 0:
        return f"block {context.loop_state.block_index}"
    return status


def public_run_control(context: ProjectContext) -> dict[str, Any]:
    control = load_run_control(context)
    return {
        "stop_after_current_step": bool(control.get("stop_after_current_step")),
        "stop_immediately": bool(control.get("stop_immediately")),
        "requested_at": str(control.get("requested_at") or "").strip() or None,
        "request_source": str(control.get("request_source") or "").strip() or None,
    }


def can_pause_from_remote(context: ProjectContext, plan_state: ExecutionPlanState) -> bool:
    control = load_run_control(context)
    status = effective_project_status(context.metadata.current_status, plan_state, context.loop_state)
    return status.startswith("running:") and not bool(control.get("stop_after_current_step"))


def can_resume_from_remote(context: ProjectContext, plan_state: ExecutionPlanState) -> bool:
    if context.loop_state.pending_checkpoint_approval:
        return False
    status = effective_project_status(context.metadata.current_status, plan_state, context.loop_state)
    if status.startswith("running:") or not plan_state.steps:
        return False
    if any(step.status != "completed" for step in plan_state.steps):
        return True
    return str(plan_state.closeout_status or "").strip().lower() != "completed"


def public_remote_control_state(context: ProjectContext, plan_state: ExecutionPlanState) -> dict[str, Any]:
    control = public_run_control(context)
    return {
        "available": True,
        "pause_mode": "after_current_step",
        "pause_requested": bool(control["stop_after_current_step"]),
        "can_pause": can_pause_from_remote(context, plan_state),
        "can_resume": can_resume_from_remote(context, plan_state),
    }


def public_execution_flow_svg(context: ProjectContext, plan_state: ExecutionPlanState) -> str:
    safe_steps = []
    for step in plan_state.steps:
        detail = mask_public_text(step.display_description or "", max_chars=96)
        if not detail and step.depends_on:
            detail = ", ".join(step.depends_on)
        if not detail and step.owned_paths:
            detail = f"{len(step.owned_paths)} owned path(s)"
        safe_steps.append(
            step.__class__(
                step_id=step.step_id,
                title=mask_public_text(step.title, max_chars=90) or step.step_id,
                display_description=detail,
                codex_description="",
                test_command="",
                success_criteria="",
                reasoning_effort=step.reasoning_effort,
                parallel_group="",
                depends_on=list(step.depends_on),
                owned_paths=[],
                status=step.status,
                started_at=step.started_at,
                completed_at=step.completed_at,
                commit_hash=None,
                notes="",
                metadata={},
            )
        )
    flow_title = mask_public_text(f"{context.metadata.display_name or context.metadata.slug} execution flow", max_chars=90)
    return execution_plan_svg(flow_title or "Execution flow", safe_steps, plan_state.execution_mode)


def public_monitor_status(context: ProjectContext, plan_state: ExecutionPlanState, log_limit: int = 8) -> dict[str, Any]:
    raw_status = str(context.metadata.current_status or "").strip()
    status = effective_project_status(context.metadata.current_status, plan_state, context.loop_state)
    if raw_status.lower().startswith("running:") and not status.startswith("running:"):
        status = raw_status
    return {
        "project": {
            "repo_id": context.metadata.repo_id,
            "display_name": mask_public_text(context.metadata.display_name or context.metadata.slug, max_chars=80),
            "slug": context.metadata.slug,
        },
        "overall_run_status": status,
        "current_phase": current_phase(context, plan_state),
        "current_block_index": max(0, int(context.loop_state.block_index or 0)),
        "current_task": {
            "title": mask_public_text(context.loop_state.current_task or "", max_chars=120),
            "step": current_step_summary(plan_state),
        },
        "latest_test_result": public_test_result(context),
        "recent_logs": project_monitor_lines(context, plan_state, limit=log_limit),
        "last_updated_at": last_updated_timestamp(context, plan_state),
        "run_control": public_run_control(context),
        "remote_control": public_remote_control_state(context, plan_state),
        "flow": {
            "available": True,
            "step_count": len(plan_state.steps),
        },
    }


def _workspace_monitor_visibility(
    context: ProjectContext,
    plan_state: ExecutionPlanState,
    *,
    include_repo_ids: set[str] | None = None,
) -> bool:
    if include_repo_ids and context.metadata.repo_id in include_repo_ids:
        return True
    raw_status = str(context.metadata.current_status or "").strip().lower()
    if raw_status.startswith("running:"):
        return True
    remote = public_remote_control_state(context, plan_state)
    status = effective_project_status(context.metadata.current_status, plan_state, context.loop_state)
    if context.loop_state.pending_checkpoint_approval:
        return True
    if remote["can_pause"] or remote["can_resume"] or remote["pause_requested"]:
        return True
    return status.startswith("running:")


def _workspace_monitor_sort_key(item: dict[str, Any]) -> tuple[int, float, str]:
    project = item.get("project", {}) if isinstance(item, dict) else {}
    remote = item.get("remote_control", {}) if isinstance(item, dict) else {}
    status = str(item.get("overall_run_status", "")).strip().lower()
    last_updated = parse_iso_datetime(str(item.get("last_updated_at", "")).strip())
    timestamp = last_updated.timestamp() if last_updated is not None else 0.0
    if status.startswith("running:"):
        priority = 0
    elif bool(remote.get("pause_requested")):
        priority = 1
    elif bool(remote.get("can_resume")):
        priority = 2
    elif bool(item.get("checkpoint_pending")):
        priority = 3
    else:
        priority = 4
    display_name = str(project.get("display_name", "")).strip().lower()
    return (priority, -timestamp, display_name)


def public_workspace_monitor_status(
    workspace_root: Path,
    *,
    orchestrator: Any | None = None,
    log_limit: int = 8,
    include_repo_ids: set[str] | None = None,
) -> dict[str, Any]:
    from .orchestrator import Orchestrator

    orchestrator = orchestrator or Orchestrator(workspace_root)
    projects: list[dict[str, Any]] = []
    last_updated_candidates: list[datetime] = []
    for project in orchestrator.list_projects():
        plan_state = orchestrator.load_execution_plan_state(project)
        if not _workspace_monitor_visibility(project, plan_state, include_repo_ids=include_repo_ids):
            continue
        payload = public_monitor_status(project, plan_state, log_limit=log_limit)
        payload["checkpoint_pending"] = bool(project.loop_state.pending_checkpoint_approval)
        projects.append(payload)
        parsed_last_updated = parse_iso_datetime(str(payload.get("last_updated_at", "")).strip())
        if parsed_last_updated is not None:
            last_updated_candidates.append(parsed_last_updated)

    projects.sort(key=_workspace_monitor_sort_key)
    running_count = sum(1 for item in projects if str(item.get("overall_run_status", "")).strip().lower().startswith("running:"))
    resume_ready_count = sum(1 for item in projects if bool(item.get("remote_control", {}).get("can_resume")))
    pause_requested_count = sum(1 for item in projects if bool(item.get("remote_control", {}).get("pause_requested")))
    checkpoint_pending_count = sum(1 for item in projects if bool(item.get("checkpoint_pending")))
    last_updated_at = max(last_updated_candidates).replace(microsecond=0).isoformat() if last_updated_candidates else None
    return {
        "workspace": {
            "project_count": len(projects),
            "running_count": running_count,
            "resume_ready_count": resume_ready_count,
            "pause_requested_count": pause_requested_count,
            "checkpoint_pending_count": checkpoint_pending_count,
        },
        "projects": projects,
        "last_updated_at": last_updated_at,
    }


def viewer_link(base_url: str, session: ShareSession, viewer_path: str = DEFAULT_VIEWER_PATH) -> str:
    normalized_base = base_url.rstrip("/")
    normalized_path = viewer_path if viewer_path.startswith("/") else f"/{viewer_path}"
    return (
        f"{normalized_base}{normalized_path}"
        f"?session={quote(session.session_id)}&token={quote(session.viewer_token)}"
    )


def viewer_access_link(base_url: str, access_token: str, viewer_path: str = DEFAULT_VIEWER_PATH) -> str:
    normalized_base = base_url.rstrip("/")
    normalized_path = viewer_path if viewer_path.startswith("/") else f"/{viewer_path}"
    return f"{normalized_base}{normalized_path}?access={quote(access_token)}"


def public_session_summary(
    workspace_root: Path,
    context: ProjectContext | None,
    session: ShareSession,
    include_token: bool = False,
    *,
    server: dict[str, Any] | None = None,
    state: ShareServerState | None | object = _UNSET,
) -> dict[str, Any]:
    if state is _UNSET:
        state = load_share_server_state(workspace_root)
    if server is None:
        server = share_server_status_payload(workspace_root)
    viewer_path = str(server.get("viewer_path") or (state.viewer_path if state is not None else DEFAULT_VIEWER_PATH))
    access_token = ensure_share_access_token(workspace_root)
    local_url = None
    local_base = str(server.get("base_url") or "").strip()
    if not local_base and bool(server.get("running")) and state is not None:
        local_base = state.base_url
    local_host = str(server.get("host") or "").strip()
    if not local_host and bool(server.get("running")) and state is not None:
        local_host = state.host
    if local_base:
        if local_host == "0.0.0.0":
            local_base = local_base.replace("http://0.0.0.0:", "http://127.0.0.1:", 1)
        local_url = viewer_access_link(local_base, access_token, viewer_path)
    public_url = None
    if server.get("share_base_url"):
        public_url = viewer_access_link(str(server["share_base_url"]), access_token, viewer_path)
    payload = {
        "session_id": session.session_id,
        "created_at": session.created_at,
        "expires_at": session.expires_at,
        "revoked_at": session.revoked_at,
        "active": session.is_active(),
        "created_by": session.created_by,
        "local_url": local_url,
    }
    if include_token:
        payload["viewer_token"] = session.viewer_token
        payload["access_token"] = access_token
    payload["share_url"] = public_url or local_url
    return payload


def workspace_share_payload(workspace_root: Path, context: ProjectContext | None = None) -> dict[str, Any]:
    sessions = load_workspace_share_sessions(workspace_root)
    state = load_share_server_state(workspace_root)
    server = share_server_status_payload(workspace_root)
    public_sessions = [
        public_session_summary(
            workspace_root,
            context,
            session,
            include_token=False,
            server=server,
            state=state,
        )
        for session in sorted(sessions, key=lambda item: item.created_at, reverse=True)
    ]
    project_active = next(
        (
            item
            for item in public_sessions
            if item.get("active")
            and context is not None
            and isinstance(item.get("project"), dict)
            and str(item["project"].get("repo_id", "")).strip() == context.metadata.repo_id
        ),
        None,
    )
    active = workspace_active_share_session(
        workspace_root,
        server=server,
        state=state,
    )
    return {
        "server": server,
        "sessions": public_sessions,
        "project_active_session": project_active,
        "active_session": active,
    }


def project_share_payload(workspace_root: Path, context: ProjectContext) -> dict[str, Any]:
    return workspace_share_payload(workspace_root, context)
