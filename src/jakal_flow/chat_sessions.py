from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any
from uuid import uuid4

from .codex_runner import CodexRunner
from .errors import JSON_PARSE_EXCEPTIONS
from .execution_control import ImmediateStopRequested, execution_scope_id, run_subprocess_capture
from .models import ExecutionPlanState, ProjectContext
from .model_providers import normalize_model_provider
from .platform_defaults import default_codex_path
from .planning import load_source_prompt_template
from .runtime_config import runtime_from_payload
from .step_models import provider_execution_preflight_error
from .utils import append_text, compact_text, decode_process_output, ensure_dir, now_utc_iso, parse_json_text, read_text, sanitized_subprocess_env, write_text


CHAT_CONVERSATION_PROMPT_FILENAME = "CHAT_CONVERSATION_PROMPT.txt"
CHAT_SESSIONS_FILENAME = "CHAT_SESSIONS.txt"
CHAT_ACTIVE_SESSION_FILENAME = "CHAT_ACTIVE_SESSION.txt"
CHAT_SESSIONS_DIRNAME = "chat_sessions"
CHAT_ACTIVE_DIRNAME = "active"
CHAT_STORAGE_LOGS_DIRNAME = "logs"
CHAT_STORAGE_MEMORY_DIRNAME = "memory"
CHAT_HOME_ENV_VAR = "JAKAL_FLOW_CHAT_HOME"
CHAT_MESSAGE_LOG_SUFFIX = ".messages.txt"
CHAT_SUMMARY_SUFFIX = ".summary.txt"
CHAT_TRANSCRIPT_SUFFIX = ".transcript.txt"
CHAT_INTERRUPTED_MESSAGE = "Response stopped."
_CHAT_REGISTRY_MEMORY_CACHE: dict[str, tuple[str, list[dict[str, Any]]]] = {}
_CHAT_ACTIVE_SESSION_MEMORY_CACHE: dict[str, tuple[str, str]] = {}
_CHAT_MESSAGES_MEMORY_CACHE: dict[str, tuple[str, list[dict[str, Any]]]] = {}
_CHAT_TEXT_MEMORY_CACHE: dict[str, tuple[str, str]] = {}
_CHAT_PAYLOAD_MEMORY_CACHE: dict[str, tuple[str, dict[str, Any]]] = {}
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


@dataclass(slots=True)
class ChatSessionMeta:
    session_id: str
    repo_id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0
    last_mode: str = "conversation"
    summary_file: str = ""
    transcript_file: str = ""
    log_file: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "repo_id": self.repo_id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message_count": self.message_count,
            "last_mode": self.last_mode,
            "summary_file": self.summary_file,
            "transcript_file": self.transcript_file,
            "log_file": self.log_file,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChatSessionMeta":
        return cls(
            session_id=str(data.get("session_id", "")).strip(),
            repo_id=str(data.get("repo_id", "")).strip(),
            title=str(data.get("title", "")).strip() or "Conversation.txt",
            created_at=str(data.get("created_at", "")).strip(),
            updated_at=str(data.get("updated_at", "")).strip(),
            message_count=max(0, int(data.get("message_count", 0) or 0)),
            last_mode=str(data.get("last_mode", "conversation")).strip() or "conversation",
            summary_file=str(data.get("summary_file", "")).strip(),
            transcript_file=str(data.get("transcript_file", "")).strip(),
            log_file=str(data.get("log_file", "")).strip(),
        )


@dataclass(slots=True)
class ChatMessageEntry:
    message_id: str
    role: str
    text: str
    created_at: str
    mode: str = "conversation"
    status: str = "completed"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "role": self.role,
            "text": self.text,
            "created_at": self.created_at,
            "mode": self.mode,
            "status": self.status,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChatMessageEntry":
        metadata = data.get("metadata", {})
        return cls(
            message_id=str(data.get("message_id", "")).strip() or f"msg-{uuid4().hex[:8]}",
            role=str(data.get("role", "assistant")).strip() or "assistant",
            text=str(data.get("text", "")).strip(),
            created_at=str(data.get("created_at", "")).strip() or now_utc_iso(),
            mode=str(data.get("mode", "conversation")).strip() or "conversation",
            status=str(data.get("status", "completed")).strip() or "completed",
            metadata=metadata if isinstance(metadata, dict) else {},
        )


def _path_signature(path: Path) -> str:
    try:
        stat_result = path.stat()
    except OSError:
        return "missing"
    return f"{stat_result.st_mtime_ns}:{stat_result.st_size}"


def _clone_chat_payload(payload: dict[str, Any]) -> dict[str, Any]:
    sessions = payload.get("sessions")
    messages = payload.get("messages")
    active_session = payload.get("active_session")
    return {
        "sessions": [dict(item) if isinstance(item, dict) else item for item in sessions] if isinstance(sessions, list) else [],
        "active_session_id": payload.get("active_session_id", ""),
        "active_session": dict(active_session) if isinstance(active_session, dict) else active_session,
        "messages": [dict(item) if isinstance(item, dict) else item for item in messages] if isinstance(messages, list) else [],
        "summary_text": str(payload.get("summary_text", "")),
        "summary_file": str(payload.get("summary_file", "")),
        "transcript_file": str(payload.get("transcript_file", "")),
        "draft_session": bool(payload.get("draft_session")),
    }


def _invalidate_chat_caches(
    context: ProjectContext,
    *,
    session_id: str = "",
    include_registry: bool = False,
    include_active: bool = False,
) -> None:
    root = chat_storage_root(context)
    if include_registry:
        _CHAT_REGISTRY_MEMORY_CACHE.pop(str(chat_sessions_registry_file(context).resolve()), None)
    if include_active:
        _CHAT_ACTIVE_SESSION_MEMORY_CACHE.pop(str(chat_active_session_file(context).resolve()), None)
    session_key = str(session_id or "").strip()
    if session_key:
        _CHAT_MESSAGES_MEMORY_CACHE.pop(str(chat_message_log_file(context, session_key).resolve()), None)
    stale_payload_keys = [
        key
        for key in _CHAT_PAYLOAD_MEMORY_CACHE
        if key.startswith(f"{root.resolve()}|{context.metadata.repo_id}|")
        and (not session_key or f"|{session_key}|" in key or key.endswith(f"|{session_key}"))
    ]
    for key in stale_payload_keys:
        _CHAT_PAYLOAD_MEMORY_CACHE.pop(key, None)


def _cached_text(path: Path) -> str:
    cache_key = str(path.resolve())
    signature = _path_signature(path)
    cached = _CHAT_TEXT_MEMORY_CACHE.get(cache_key)
    if cached is not None and cached[0] == signature:
        return cached[1]
    value = read_text(path)
    _CHAT_TEXT_MEMORY_CACHE[cache_key] = (signature, value)
    return value


def _default_chat_home_root(context: ProjectContext) -> Path:
    module_path = Path(__file__).resolve()
    for parent in module_path.parents:
        if (parent / "pyproject.toml").exists() and (parent / "src" / "jakal_flow").exists():
            return parent / CHAT_SESSIONS_DIRNAME
    return context.paths.workspace_root / CHAT_SESSIONS_DIRNAME


def chat_storage_root(context: ProjectContext) -> Path:
    override = str(os.environ.get(CHAT_HOME_ENV_VAR, "")).strip()
    if override:
        return Path(override).expanduser().resolve()
    return _default_chat_home_root(context)


def chat_sessions_registry_file(context: ProjectContext) -> Path:
    return chat_storage_root(context) / CHAT_SESSIONS_FILENAME


def chat_active_session_file(context: ProjectContext) -> Path:
    return chat_storage_root(context) / CHAT_ACTIVE_DIRNAME / f"{context.metadata.repo_id}.txt"


def chat_logs_dir(context: ProjectContext) -> Path:
    return chat_storage_root(context) / CHAT_STORAGE_LOGS_DIRNAME


def chat_memory_dir(context: ProjectContext) -> Path:
    return chat_storage_root(context) / CHAT_STORAGE_MEMORY_DIRNAME


def _legacy_chat_sessions_registry_file(context: ProjectContext) -> Path:
    return context.paths.state_dir / CHAT_SESSIONS_FILENAME


def _legacy_chat_active_session_file(context: ProjectContext) -> Path:
    return context.paths.state_dir / CHAT_ACTIVE_SESSION_FILENAME


def _legacy_chat_logs_dir(context: ProjectContext) -> Path:
    return context.paths.logs_dir / CHAT_SESSIONS_DIRNAME


def _legacy_chat_memory_dir(context: ProjectContext) -> Path:
    return context.paths.memory_dir / CHAT_SESSIONS_DIRNAME


def chat_message_log_file(context: ProjectContext, session_id: str) -> Path:
    return chat_logs_dir(context) / f"{session_id}{CHAT_MESSAGE_LOG_SUFFIX}"


def _sanitize_chat_filename_fragment(value: str) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    if normalized.lower().endswith(".txt"):
        normalized = normalized[:-4].rstrip()
    normalized = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", normalized)
    normalized = normalized.rstrip(". ").strip()
    normalized = compact_text(normalized, max_chars=72)
    if not normalized:
        normalized = "Conversation"
    if normalized.upper() in _WINDOWS_RESERVED_NAMES:
        normalized = f"{normalized} chat"
    return normalized


def _timestamp_slug_from(value: str) -> str:
    digits = "".join(char for char in str(value or "") if char.isdigit())
    return digits[:14] or _session_timestamp_slug()


def _session_title_filename(title_hint: str, created_at: str) -> str:
    return f"{_sanitize_chat_filename_fragment(title_hint)} {_timestamp_slug_from(created_at)}.txt"


def _session_memory_stem(title: str, session_id: str, created_at: str) -> str:
    current = Path(str(title or "").strip()).stem.strip()
    if current:
        return current
    return Path(_session_title_filename(session_id, created_at)).stem


def _session_summary_file(context: ProjectContext, title: str, session_id: str, created_at: str) -> Path:
    return chat_memory_dir(context) / f"{_session_memory_stem(title, session_id, created_at)}{CHAT_SUMMARY_SUFFIX}"


def _session_transcript_file(context: ProjectContext, title: str, created_at: str) -> Path:
    normalized_title = str(title or "").strip() or _session_title_filename("Conversation", created_at)
    return chat_memory_dir(context) / normalized_title


def _safe_chat_mode(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"review", "debugger", "merger"}:
        return normalized
    return "conversation"


def _conversation_user_message(user_message: str, mode: str = "conversation") -> str:
    cleaned = str(user_message or "").strip()
    normalized_mode = _safe_chat_mode(mode)
    if normalized_mode != "review":
        return cleaned
    return (
        "Review the following code, diff, or implementation request.\n"
        "1. Summarize what it does.\n"
        "2. Evaluate correctness, maintainability, and risks.\n"
        "3. Suggest concrete improvements and next steps.\n"
        "4. Respond in the same language as the user's message when practical.\n\n"
        "User content:\n"
        f"{cleaned}"
    ).strip()


def _session_title(value: str) -> str:
    return _session_title_filename(str(value or "").strip() or "Conversation", now_utc_iso())


def _session_timestamp_slug() -> str:
    return "".join(char for char in now_utc_iso() if char.isdigit())[:14] or "00000000000000"


def _read_jsonl_txt(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for line in read_text(path).splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            payload = parse_json_text(raw)
        except JSON_PARSE_EXCEPTIONS:
            continue
        if isinstance(payload, dict):
            items.append(payload)
    return items


def _iter_text_lines_from_end(path: Path, chunk_size: int = 8192):
    file_size = path.stat().st_size
    if file_size <= 0:
        return
    with path.open("rb") as handle:
        position = file_size
        remainder = b""
        while position > 0:
            read_size = min(chunk_size, position)
            position -= read_size
            handle.seek(position)
            chunk = handle.read(read_size)
            buffer = chunk + remainder
            parts = buffer.split(b"\n")
            remainder = parts[0]
            for line in reversed(parts[1:]):
                yield line.rstrip(b"\r").decode("utf-8", errors="replace")
        if remainder:
            yield remainder.rstrip(b"\r").decode("utf-8", errors="replace")


def _read_jsonl_txt_tail(path: Path, limit: int) -> list[dict[str, Any]]:
    if limit <= 0 or not path.exists():
        return []
    items: list[dict[str, Any]] = []
    for line in _iter_text_lines_from_end(path):
        raw = line.strip()
        if not raw:
            continue
        try:
            payload = parse_json_text(raw)
        except JSON_PARSE_EXCEPTIONS:
            continue
        if isinstance(payload, dict):
            items.append(payload)
        if len(items) >= limit:
            break
    items.reverse()
    return items


def _write_jsonl_txt(path: Path, items: list[dict[str, Any]]) -> None:
    content = "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in items if isinstance(item, dict))
    write_text(path, f"{content}\n" if content else "")


def _read_registry_sessions(path: Path) -> list[ChatSessionMeta]:
    cache_key = str(path.resolve())
    signature = _path_signature(path)
    cached = _CHAT_REGISTRY_MEMORY_CACHE.get(cache_key)
    if cached is not None and cached[0] == signature:
        return [ChatSessionMeta.from_dict(item) for item in cached[1]]
    sessions = [
        ChatSessionMeta.from_dict(item)
        for item in _read_jsonl_txt(path)
        if str(item.get("session_id", "")).strip()
    ]
    sessions.sort(key=lambda item: (item.updated_at, item.created_at, item.session_id), reverse=True)
    _CHAT_REGISTRY_MEMORY_CACHE[cache_key] = (signature, [item.to_dict() for item in sessions])
    return sessions


def _save_registry_sessions(path: Path, sessions: list[ChatSessionMeta]) -> None:
    ensure_dir(path.parent)
    deduped: dict[str, ChatSessionMeta] = {session.session_id: session for session in sessions if session.session_id}
    ordered = sorted(deduped.values(), key=lambda item: (item.updated_at, item.created_at, item.session_id), reverse=True)
    _write_jsonl_txt(path, [item.to_dict() for item in ordered])
    _CHAT_REGISTRY_MEMORY_CACHE[str(path.resolve())] = (
        _path_signature(path),
        [item.to_dict() for item in ordered],
    )


def _relocate_session_memory_files(context: ProjectContext, session: ChatSessionMeta) -> ChatSessionMeta:
    title = str(session.title or "").strip() or _session_title_filename("Conversation", session.created_at)
    if not title.lower().endswith(".txt"):
        title = _session_title_filename(title, session.created_at)
    session.title = title

    target_summary = _session_summary_file(context, session.title, session.session_id, session.created_at)
    target_transcript = _session_transcript_file(context, session.title, session.created_at)
    target_log = chat_message_log_file(context, session.session_id)
    ensure_dir(target_summary.parent)
    ensure_dir(target_transcript.parent)
    ensure_dir(target_log.parent)

    for source_raw, target in (
        (session.summary_file, target_summary),
        (session.transcript_file, target_transcript),
        (session.log_file, target_log),
    ):
        source = Path(str(source_raw or "").strip()) if str(source_raw or "").strip() else None
        if source is None or not source.exists():
            continue
        if source.resolve() == target.resolve():
            continue
        if target.exists():
            if source.read_bytes() == target.read_bytes():
                source.unlink(missing_ok=True)
                continue
            target = target.with_name(f"{target.stem}-{session.session_id[:6]}{target.suffix}")
        shutil.move(str(source), str(target))

    session.summary_file = str(target_summary)
    session.transcript_file = str(target_transcript)
    session.log_file = str(target_log)
    return session


def _cleanup_legacy_chat_dirs(context: ProjectContext) -> None:
    for directory in (_legacy_chat_logs_dir(context), _legacy_chat_memory_dir(context)):
        if not directory.exists():
            continue
        try:
            next(directory.iterdir())
        except StopIteration:
            directory.rmdir()
        except OSError:
            continue


def _migrate_legacy_project_chat_storage(context: ProjectContext) -> None:
    legacy_registry = _legacy_chat_sessions_registry_file(context)
    legacy_active = _legacy_chat_active_session_file(context)
    has_legacy_state = (
        legacy_registry.exists()
        or legacy_active.exists()
        or _legacy_chat_logs_dir(context).exists()
        or _legacy_chat_memory_dir(context).exists()
    )
    if not has_legacy_state:
        return

    global_sessions = _read_registry_sessions(chat_sessions_registry_file(context))
    by_id: dict[str, ChatSessionMeta] = {session.session_id: session for session in global_sessions}
    migrated_any = False
    for session in _read_registry_sessions(legacy_registry):
        session.repo_id = session.repo_id or context.metadata.repo_id
        session = _relocate_session_memory_files(context, session)
        by_id[session.session_id] = session
        migrated_any = True

    if migrated_any:
        _save_registry_sessions(chat_sessions_registry_file(context), list(by_id.values()))

    active_session_id = read_text(legacy_active).strip()
    if active_session_id:
        save_active_chat_session_id(context, active_session_id)

    legacy_registry.unlink(missing_ok=True)
    legacy_active.unlink(missing_ok=True)
    _cleanup_legacy_chat_dirs(context)


def load_chat_sessions(context: ProjectContext) -> list[ChatSessionMeta]:
    _migrate_legacy_project_chat_storage(context)
    sessions = [
        session
        for session in _read_registry_sessions(chat_sessions_registry_file(context))
        if session.repo_id == context.metadata.repo_id
    ]
    return sessions


def save_chat_sessions(context: ProjectContext, sessions: list[ChatSessionMeta]) -> None:
    current_repo_id = context.metadata.repo_id
    existing = _read_registry_sessions(chat_sessions_registry_file(context))
    preserved = [session for session in existing if session.repo_id != current_repo_id]
    normalized: list[ChatSessionMeta] = []
    for session in sessions:
        if not session.session_id:
            continue
        session.repo_id = current_repo_id
        normalized.append(_relocate_session_memory_files(context, session))
    _save_registry_sessions(chat_sessions_registry_file(context), [*preserved, *normalized])
    _invalidate_chat_caches(context, include_registry=False)


def load_active_chat_session_id(context: ProjectContext) -> str:
    path = chat_active_session_file(context)
    cache_key = str(path.resolve())
    signature = _path_signature(path)
    cached = _CHAT_ACTIVE_SESSION_MEMORY_CACHE.get(cache_key)
    if cached is not None and cached[0] == signature:
        return cached[1]
    session_id = read_text(path).strip()
    _CHAT_ACTIVE_SESSION_MEMORY_CACHE[cache_key] = (signature, session_id)
    return session_id


def save_active_chat_session_id(context: ProjectContext, session_id: str) -> None:
    path = chat_active_session_file(context)
    normalized = str(session_id or "").strip()
    current_value = load_active_chat_session_id(context)
    if current_value == normalized and path.exists():
        return
    write_text(path, f"{normalized}\n")
    _CHAT_ACTIVE_SESSION_MEMORY_CACHE[str(path.resolve())] = (_path_signature(path), normalized)
    _invalidate_chat_caches(context, session_id=normalized, include_active=False)


def _session_by_id(context: ProjectContext) -> dict[str, ChatSessionMeta]:
    return {session.session_id: session for session in load_chat_sessions(context)}


def create_chat_session(context: ProjectContext, *, title_hint: str = "") -> ChatSessionMeta:
    created_at = now_utc_iso()
    session_id = f"chat-{_session_timestamp_slug()}-{uuid4().hex[:6]}"
    title = _session_title_filename(title_hint or "Conversation", created_at)
    summary_path = _session_summary_file(context, title, session_id, created_at)
    transcript_path = _session_transcript_file(context, title, created_at)
    log_path = chat_message_log_file(context, session_id)
    for directory in (summary_path.parent, transcript_path.parent, log_path.parent):
        ensure_dir(directory)
    session = ChatSessionMeta(
        session_id=session_id,
        repo_id=context.metadata.repo_id,
        title=title,
        created_at=created_at,
        updated_at=created_at,
        message_count=0,
        last_mode="conversation",
        summary_file=str(summary_path),
        transcript_file=str(transcript_path),
        log_file=str(log_path),
    )
    sessions = load_chat_sessions(context)
    sessions.append(session)
    save_chat_sessions(context, sessions)
    save_active_chat_session_id(context, session.session_id)
    rebuild_chat_session_files(context, session.session_id)
    return session


def resolve_chat_session(
    context: ProjectContext,
    *,
    session_id: str = "",
    create_new: bool = False,
    title_hint: str = "",
) -> ChatSessionMeta:
    session_map = _session_by_id(context)
    requested_id = str(session_id or "").strip()
    if not create_new and requested_id and requested_id in session_map:
        save_active_chat_session_id(context, requested_id)
        return session_map[requested_id]
    if not create_new:
        active_session_id = load_active_chat_session_id(context)
        if active_session_id and active_session_id in session_map:
            return session_map[active_session_id]
        sessions = load_chat_sessions(context)
        if sessions:
            save_active_chat_session_id(context, sessions[0].session_id)
            return sessions[0]
    return create_chat_session(context, title_hint=title_hint)


def load_chat_messages(
    context: ProjectContext,
    session_id: str,
    *,
    limit: int | None = None,
) -> list[ChatMessageEntry]:
    session_key = str(session_id or "").strip()
    if not session_key:
        return []
    log_file = chat_message_log_file(context, session_key)
    cache_key = str(log_file.resolve())
    signature = f"{_path_signature(log_file)}|{int(limit) if isinstance(limit, int) else -1}"
    cached = _CHAT_MESSAGES_MEMORY_CACHE.get(cache_key)
    if cached is not None and cached[0] == signature:
        return [ChatMessageEntry.from_dict(item) for item in cached[1]]
    if limit is not None and limit > 0:
        raw_items = _read_jsonl_txt_tail(log_file, limit)
    else:
        raw_items = _read_jsonl_txt(log_file)
    messages = [ChatMessageEntry.from_dict(item) for item in raw_items]
    _CHAT_MESSAGES_MEMORY_CACHE[cache_key] = (signature, [item.to_dict() for item in messages])
    return messages


def _save_chat_message(
    context: ProjectContext,
    session_id: str,
    *,
    role: str,
    text: str,
    mode: str,
    status: str = "completed",
    metadata: dict[str, Any] | None = None,
) -> ChatMessageEntry:
    session_key = str(session_id or "").strip()
    if not session_key:
        raise ValueError("session_id is required.")
    entry = ChatMessageEntry(
        message_id=f"msg-{_session_timestamp_slug()}-{uuid4().hex[:6]}",
        role=str(role or "assistant").strip() or "assistant",
        text=str(text or "").strip(),
        created_at=now_utc_iso(),
        mode=_safe_chat_mode(mode),
        status=str(status or "completed").strip() or "completed",
        metadata=metadata if isinstance(metadata, dict) else {},
    )
    log_path = chat_message_log_file(context, session_key)
    ensure_dir(log_path.parent)
    append_text(log_path, f"{json.dumps(entry.to_dict(), ensure_ascii=False, sort_keys=True)}\n")
    _invalidate_chat_caches(context, session_id=session_key)
    _sync_chat_session_metadata(
        context,
        session_key,
        title_hint=entry.text if entry.role == "user" else "",
        last_mode=entry.mode,
    )
    return entry


def save_chat_message(
    context: ProjectContext,
    session_id: str,
    *,
    role: str,
    text: str,
    mode: str,
    status: str = "completed",
    metadata: dict[str, Any] | None = None,
) -> ChatMessageEntry:
    return _save_chat_message(
        context,
        session_id,
        role=role,
        text=text,
        mode=mode,
        status=status,
        metadata=metadata,
    )


def _sync_chat_session_metadata(
    context: ProjectContext,
    session_id: str,
    *,
    title_hint: str = "",
    last_mode: str = "conversation",
) -> ChatSessionMeta | None:
    session_key = str(session_id or "").strip()
    if not session_key:
        return None
    sessions = load_chat_sessions(context)
    by_id = {session.session_id: session for session in sessions}
    session = by_id.get(session_key)
    if session is None:
        return None
    messages = load_chat_messages(context, session_key)
    session.updated_at = now_utc_iso()
    session.message_count = len(messages)
    session.last_mode = _safe_chat_mode(last_mode)
    if title_hint and (session.title == "Conversation" or session.message_count <= 1):
        session.title = _session_title_filename(title_hint, session.created_at)
    session.repo_id = context.metadata.repo_id
    session = _relocate_session_memory_files(context, session)
    session.log_file = str(chat_message_log_file(context, session_key))
    by_id[session_key] = session
    save_chat_sessions(context, list(by_id.values()))
    save_active_chat_session_id(context, session_key)
    return session


def rebuild_chat_session_files(context: ProjectContext, session_id: str) -> None:
    session_map = _session_by_id(context)
    session = session_map.get(str(session_id or "").strip())
    if session is None:
        return
    messages = load_chat_messages(context, session.session_id)
    summary_path = Path(session.summary_file or _session_summary_file(context, session.title, session.session_id, session.created_at))
    transcript_path = Path(session.transcript_file or _session_transcript_file(context, session.title, session.created_at))
    ensure_dir(summary_path.parent)
    ensure_dir(transcript_path.parent)

    transcript_lines = [
        "# Chat Transcript",
        "",
        f"- Session ID: {session.session_id}",
        f"- Title: {session.title}",
        f"- Created At: {session.created_at}",
        f"- Updated At: {session.updated_at}",
        f"- Message Count: {len(messages)}",
        "",
    ]
    for entry in messages:
        transcript_lines.extend(
            [
                f"## {entry.created_at} | {entry.role} | {entry.mode} | {entry.status}",
                entry.text or "(empty)",
                "",
            ]
        )
    write_text(transcript_path, "\n".join(transcript_lines).rstrip() + "\n")

    summary_lines = [
        "# Chat Session Summary",
        "",
        "Use this summary file together with the recent transcript to continue the same conversation coherently.",
        "",
        f"- Session ID: {session.session_id}",
        f"- Title: {session.title}",
        f"- Created At: {session.created_at}",
        f"- Updated At: {session.updated_at}",
        f"- Message Count: {len(messages)}",
        f"- Last Mode: {session.last_mode}",
        "",
        "## Rolling Summary",
    ]
    if messages:
        for entry in messages[-12:]:
            summary_lines.append(
                f"- {entry.created_at} | {entry.role} | {entry.mode}: "
                f"{compact_text(' '.join(entry.text.split()), max_chars=220) or '(empty)'}"
            )
    else:
        summary_lines.append("- No messages yet.")
    summary_lines.extend(["", f"Transcript File: {transcript_path}"])
    write_text(summary_path, "\n".join(summary_lines).rstrip() + "\n")
    _CHAT_TEXT_MEMORY_CACHE[str(summary_path.resolve())] = (_path_signature(summary_path), read_text(summary_path))
    _invalidate_chat_caches(context, session_id=session.session_id)


def chat_payload(
    context: ProjectContext,
    *,
    session_id: str = "",
    activate: bool = False,
    message_limit: int = 80,
    include_messages: bool = True,
    include_summary: bool = True,
) -> dict[str, Any]:
    sessions = load_chat_sessions(context)
    session_map = {session.session_id: session for session in sessions}
    active_session_id = str(session_id or "").strip()
    if active_session_id and active_session_id in session_map:
        if activate:
            save_active_chat_session_id(context, active_session_id)
    else:
        active_session_id = load_active_chat_session_id(context)
        if active_session_id not in session_map:
            active_session_id = sessions[0].session_id if sessions else ""
            if active_session_id and activate:
                save_active_chat_session_id(context, active_session_id)
    active_session = session_map.get(active_session_id)
    active_log_signature = _path_signature(chat_message_log_file(context, active_session_id)) if active_session_id else "none"
    summary_signature = _path_signature(Path(active_session.summary_file)) if active_session and active_session.summary_file else "none"
    registry_signature = _path_signature(chat_sessions_registry_file(context))
    active_file_signature = _path_signature(chat_active_session_file(context))
    payload_cache_key = (
        f"{chat_storage_root(context).resolve()}|{context.metadata.repo_id}|{active_session_id}|"
        f"{message_limit}|{int(include_messages)}|{int(include_summary)}|{int(activate)}"
    )
    payload_signature = "|".join(
        (
            registry_signature,
            active_file_signature,
            active_log_signature,
            summary_signature,
        )
    )
    cached_payload = _CHAT_PAYLOAD_MEMORY_CACHE.get(payload_cache_key)
    if cached_payload is not None and cached_payload[0] == payload_signature:
        return _clone_chat_payload(cached_payload[1])
    messages = [
        entry.to_dict()
        for entry in load_chat_messages(context, active_session_id, limit=message_limit)
    ] if active_session and include_messages else []
    summary_text = (
        _cached_text(Path(active_session.summary_file))
        if active_session and active_session.summary_file and include_summary
        else ""
    )
    transcript_file = active_session.transcript_file if active_session else ""
    summary_file = active_session.summary_file if active_session else ""
    payload = {
        "sessions": [session.to_dict() for session in sessions],
        "active_session_id": active_session_id,
        "active_session": active_session.to_dict() if active_session else None,
        "messages": messages,
        "summary_text": compact_text(summary_text, max_chars=4000),
        "summary_file": summary_file,
        "transcript_file": transcript_file,
        "draft_session": not bool(active_session_id),
    }
    _CHAT_PAYLOAD_MEMORY_CACHE[payload_cache_key] = (payload_signature, _clone_chat_payload(payload))
    return payload


def _chat_project_summary(context: ProjectContext, plan_state: ExecutionPlanState) -> str:
    lines = [
        f"Project: {context.metadata.display_name or context.metadata.slug}",
        f"Directory: {context.metadata.repo_path}",
        f"Branch: {context.metadata.branch}",
        f"Status: {context.metadata.current_status}",
        f"Plan title: {plan_state.plan_title.strip() or 'None'}",
        f"Saved prompt: {compact_text(plan_state.project_prompt.strip(), max_chars=500) or 'None'}",
        f"Closeout status: {plan_state.closeout_status}",
    ]
    return "\n".join(lines)


def _recent_transcript_for_prompt(messages: list[ChatMessageEntry]) -> str:
    if not messages:
        return "No prior messages."
    lines: list[str] = []
    for entry in messages[-8:]:
        lines.extend(
            [
                f"{entry.created_at} | {entry.role} | {entry.mode} | {entry.status}",
                compact_text(entry.text, max_chars=1200) or "(empty)",
                "",
            ]
        )
    return "\n".join(lines).strip() or "No prior messages."


def build_conversation_prompt(
    context: ProjectContext,
    *,
    plan_state: ExecutionPlanState,
    session: ChatSessionMeta,
    prior_summary: str,
    recent_messages: list[ChatMessageEntry],
    user_message: str,
) -> str:
    template = load_source_prompt_template(CHAT_CONVERSATION_PROMPT_FILENAME)
    return template.format(
        repo_dir=context.paths.repo_dir,
        docs_dir=context.paths.docs_dir,
        session_id=session.session_id,
        summary_file=session.summary_file,
        transcript_file=session.transcript_file,
        project_summary=_chat_project_summary(context, plan_state),
        plan_snapshot=compact_text(read_text(context.paths.plan_file), max_chars=3000) or "No saved plan snapshot.",
        scope_guard=compact_text(read_text(context.paths.scope_guard_file), max_chars=2500) or "No scope guard recorded.",
        research_notes=compact_text(read_text(context.paths.research_notes_file), max_chars=2500) or "No research notes recorded.",
        prior_summary=compact_text(prior_summary, max_chars=3500) or "No prior conversation summary.",
        recent_transcript=_recent_transcript_for_prompt(recent_messages),
        user_message=compact_text(user_message, max_chars=2500) or "No user message provided.",
    )


def _chat_run_error_message(error_text: str, diagnostics: dict[str, Any] | None = None) -> str:
    details: list[str] = []
    if isinstance(diagnostics, dict):
        for attempt in diagnostics.get("attempts", []):
            if not isinstance(attempt, dict):
                continue
            stderr_excerpt = str(attempt.get("stderr_excerpt", "")).strip()
            last_message_excerpt = str(attempt.get("last_message_excerpt", "")).strip()
            if stderr_excerpt:
                details.append(stderr_excerpt)
            elif last_message_excerpt:
                details.append(last_message_excerpt)
    combined = "\n".join(part for part in [str(error_text or "").strip(), *details] if part)
    return compact_text(combined, max_chars=1400) or "Conversation mode could not produce a reply."


def _normalize_conversation_reply_text(text: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""

    # Conversation mode should stay readable in the desktop pane.
    cleaned = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda match: match.group(1).strip(), cleaned)
    cleaned = re.sub(r"^\s{0,3}#{1,6}\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\*\*(.+?)\*\*", lambda match: match.group(1).strip(), cleaned)
    cleaned = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", lambda match: match.group(1).strip(), cleaned)
    cleaned = re.sub(r"^\s*[-*]\s+", "- ", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _conversation_context(context: ProjectContext) -> ProjectContext:
    raw_chat_provider = str(getattr(context.runtime, "chat_model_provider", "") or "").strip().lower()
    raw_chat_model = str(getattr(context.runtime, "chat_model", "") or "").strip().lower()
    raw_chat_local_provider = str(getattr(context.runtime, "chat_local_model_provider", "") or "").strip().lower()
    if not raw_chat_provider and not raw_chat_model:
        return context

    current_provider = normalize_model_provider(getattr(context.runtime, "model_provider", ""))
    payload: dict[str, Any] = {}
    if raw_chat_provider:
        chat_provider = normalize_model_provider(raw_chat_provider, fallback=current_provider or "openai")
        payload["model_provider"] = chat_provider
        if chat_provider in {"oss", "ollama"} and raw_chat_local_provider:
            payload["local_model_provider"] = raw_chat_local_provider
        if chat_provider != current_provider:
            payload["provider_base_url"] = ""
            payload["provider_api_key_env"] = ""
            payload["codex_path"] = default_codex_path(chat_provider)
    if raw_chat_model:
        payload["model"] = raw_chat_model
        payload["model_slug_input"] = raw_chat_model
        payload["model_preset"] = ""
        payload["model_selection_mode"] = "slug"
    if not payload:
        return context

    runtime = runtime_from_payload(payload, defaults=context.runtime.to_dict())
    return ProjectContext(
        metadata=context.metadata,
        runtime=runtime,
        paths=context.paths,
        loop_state=context.loop_state,
    )


def _run_conversation_reply(
    context: ProjectContext,
    *,
    prompt: str,
    session_id: str,
) -> tuple[int, str]:
    runner = CodexRunner(context.runtime.codex_path)
    formatted_prompt = runner._format_prompt(context, prompt)
    provider = normalize_model_provider(getattr(context.runtime, "model_provider", ""))
    backend = runner._backend_kind(provider)
    preflight_error = provider_execution_preflight_error(
        provider,
        codex_path=runner.codex_path,
        repo_dir=context.paths.repo_dir,
        provider_api_key_env=str(getattr(context.runtime, "provider_api_key_env", "") or "").strip(),
        model=str(getattr(context.runtime, "model", "") or getattr(context.runtime, "model_slug_input", "")).strip(),
    )
    if preflight_error:
        return 1, preflight_error

    child_env = sanitized_subprocess_env(runner._provider_environment(context, backend=backend))
    temp_file = Path(tempfile.gettempdir()) / f"{session_id}-{uuid4().hex[:8]}.txt"
    scope_id = execution_scope_id(context)
    stdout = ""
    try:
        with runner._execution_layout(context, temp_file) as execution_layout:
            command = runner._build_command(
                context,
                backend=backend,
                output_file=execution_layout.output_file,
                search_enabled=False,
                reasoning_effort=context.runtime.effort,
                prompt_text=formatted_prompt,
                execution_layout=execution_layout,
            )
            completed = run_subprocess_capture(
                command,
                scope_id=scope_id,
                label=f"{backend.title()} chat",
                cwd=execution_layout.repo_dir,
                input_bytes=None if backend in {"claude", "qwen"} else formatted_prompt.encode("utf-8"),
                env=child_env,
            )
            stdout = decode_process_output(completed.stdout)
            if backend == "codex":
                runner._sync_output_file(execution_layout.output_file, temp_file)
            elif backend == "gemini":
                runner._write_gemini_output_file(temp_file, stdout)
            elif backend == "claude":
                runner._write_claude_output_file(temp_file, stdout)
            elif backend == "qwen":
                runner._write_qwen_output_file(temp_file, stdout)
            reply_text = read_text(temp_file).strip()
            if not reply_text and stdout.strip():
                reply_text = compact_text(stdout, max_chars=4000)
            return completed.returncode, reply_text
    finally:
        temp_file.unlink(missing_ok=True)


def execute_conversation_turn(
    context: ProjectContext,
    *,
    plan_state: ExecutionPlanState,
    user_message: str,
    mode: str = "conversation",
    session_id: str = "",
    create_new_session: bool = False,
) -> dict[str, Any]:
    cleaned_user_message = str(user_message or "").strip()
    if not cleaned_user_message:
        raise ValueError("message is required.")
    conversation_mode = _safe_chat_mode(mode)
    prompt_user_message = _conversation_user_message(cleaned_user_message, conversation_mode)
    session = resolve_chat_session(
        context,
        session_id=session_id,
        create_new=create_new_session,
        title_hint=cleaned_user_message,
    )
    prior_messages = load_chat_messages(context, session.session_id)
    prior_summary = read_text(Path(session.summary_file)) if session.summary_file else ""
    user_entry = _save_chat_message(
        context,
        session.session_id,
        role="user",
        text=cleaned_user_message,
        mode=conversation_mode,
    )
    prompt = build_conversation_prompt(
        context,
        plan_state=plan_state,
        session=session,
        prior_summary=prior_summary,
        recent_messages=[*prior_messages[-7:], user_entry],
        user_message=prompt_user_message,
    )
    conversation_context = _conversation_context(context)
    interrupted = False
    try:
        returncode, assistant_text = _run_conversation_reply(
            conversation_context,
            prompt=prompt,
            session_id=session.session_id,
        )
    except ImmediateStopRequested:
        interrupted = True
        returncode = 130
        assistant_text = CHAT_INTERRUPTED_MESSAGE
    assistant_text = _normalize_conversation_reply_text(assistant_text)
    error = ""
    role = "assistant"
    message_status = "completed"
    metadata: dict[str, Any] = {
        "returncode": int(returncode),
    }
    if interrupted:
        role = "system"
        message_status = "cancelled"
        metadata["interrupted"] = True
    elif returncode != 0 or not assistant_text:
        error = _chat_run_error_message(assistant_text)
        assistant_text = error
        role = "system"
        message_status = "failed"
    _save_chat_message(
        context,
        session.session_id,
        role=role,
        text=assistant_text,
        mode=conversation_mode,
        status=message_status,
        metadata=metadata,
    )
    rebuild_chat_session_files(context, session.session_id)
    return {
        "chat": chat_payload(context, session_id=session.session_id, activate=True),
        "error": error,
        "interrupted": interrupted,
    }
