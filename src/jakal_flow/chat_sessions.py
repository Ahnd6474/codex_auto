from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import tempfile
from typing import Any
from uuid import uuid4

from .codex_runner import CodexRunner
from .execution_control import execution_scope_id, run_subprocess_capture
from .models import ExecutionPlanState, ProjectContext
from .model_providers import normalize_model_provider
from .planning import load_source_prompt_template
from .step_models import provider_execution_preflight_error
from .utils import append_text, compact_text, decode_process_output, ensure_dir, now_utc_iso, parse_json_text, read_text, sanitized_subprocess_env, write_text


CHAT_CONVERSATION_PROMPT_FILENAME = "CHAT_CONVERSATION_PROMPT.txt"
CHAT_SESSIONS_FILENAME = "CHAT_SESSIONS.txt"
CHAT_ACTIVE_SESSION_FILENAME = "CHAT_ACTIVE_SESSION.txt"
CHAT_SESSIONS_DIRNAME = "chat_sessions"
CHAT_MESSAGE_LOG_SUFFIX = ".messages.txt"
CHAT_SUMMARY_SUFFIX = ".summary.txt"
CHAT_TRANSCRIPT_SUFFIX = ".transcript.txt"


@dataclass(slots=True)
class ChatSessionMeta:
    session_id: str
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
            title=str(data.get("title", "")).strip() or "Conversation",
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


def chat_sessions_registry_file(context: ProjectContext) -> Path:
    return context.paths.state_dir / CHAT_SESSIONS_FILENAME


def chat_active_session_file(context: ProjectContext) -> Path:
    return context.paths.state_dir / CHAT_ACTIVE_SESSION_FILENAME


def chat_logs_dir(context: ProjectContext) -> Path:
    return context.paths.logs_dir / CHAT_SESSIONS_DIRNAME


def chat_memory_dir(context: ProjectContext) -> Path:
    return context.paths.memory_dir / CHAT_SESSIONS_DIRNAME


def chat_message_log_file(context: ProjectContext, session_id: str) -> Path:
    return chat_logs_dir(context) / f"{session_id}{CHAT_MESSAGE_LOG_SUFFIX}"


def chat_summary_file(context: ProjectContext, session_id: str) -> Path:
    return chat_memory_dir(context) / f"{session_id}{CHAT_SUMMARY_SUFFIX}"


def chat_transcript_file(context: ProjectContext, session_id: str) -> Path:
    return chat_memory_dir(context) / f"{session_id}{CHAT_TRANSCRIPT_SUFFIX}"


def _safe_chat_mode(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"debugger", "merger"}:
        return normalized
    return "conversation"


def _session_title(value: str) -> str:
    normalized = " ".join(str(value or "").split())
    return compact_text(normalized, max_chars=72) or "Conversation"


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
        except Exception:
            continue
        if isinstance(payload, dict):
            items.append(payload)
    return items


def _write_jsonl_txt(path: Path, items: list[dict[str, Any]]) -> None:
    content = "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in items if isinstance(item, dict))
    write_text(path, f"{content}\n" if content else "")


def load_chat_sessions(context: ProjectContext) -> list[ChatSessionMeta]:
    sessions = [
        ChatSessionMeta.from_dict(item)
        for item in _read_jsonl_txt(chat_sessions_registry_file(context))
        if str(item.get("session_id", "")).strip()
    ]
    sessions.sort(key=lambda item: (item.updated_at, item.created_at, item.session_id), reverse=True)
    return sessions


def save_chat_sessions(context: ProjectContext, sessions: list[ChatSessionMeta]) -> None:
    ensure_dir(chat_sessions_registry_file(context).parent)
    deduped: dict[str, ChatSessionMeta] = {session.session_id: session for session in sessions if session.session_id}
    ordered = sorted(deduped.values(), key=lambda item: (item.updated_at, item.created_at, item.session_id), reverse=True)
    _write_jsonl_txt(chat_sessions_registry_file(context), [item.to_dict() for item in ordered])


def load_active_chat_session_id(context: ProjectContext) -> str:
    return read_text(chat_active_session_file(context)).strip()


def save_active_chat_session_id(context: ProjectContext, session_id: str) -> None:
    write_text(chat_active_session_file(context), f"{str(session_id or '').strip()}\n")


def _session_by_id(context: ProjectContext) -> dict[str, ChatSessionMeta]:
    return {session.session_id: session for session in load_chat_sessions(context)}


def create_chat_session(context: ProjectContext, *, title_hint: str = "") -> ChatSessionMeta:
    created_at = now_utc_iso()
    session_id = f"chat-{_session_timestamp_slug()}-{uuid4().hex[:6]}"
    summary_path = chat_summary_file(context, session_id)
    transcript_path = chat_transcript_file(context, session_id)
    log_path = chat_message_log_file(context, session_id)
    for directory in (summary_path.parent, transcript_path.parent, log_path.parent):
        ensure_dir(directory)
    session = ChatSessionMeta(
        session_id=session_id,
        title=_session_title(title_hint),
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
    messages = [ChatMessageEntry.from_dict(item) for item in _read_jsonl_txt(chat_message_log_file(context, session_key))]
    if limit is not None and limit > 0 and len(messages) > limit:
        return messages[-limit:]
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
        session.title = _session_title(title_hint)
    session.summary_file = str(chat_summary_file(context, session_key))
    session.transcript_file = str(chat_transcript_file(context, session_key))
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
    summary_path = Path(session.summary_file or chat_summary_file(context, session.session_id))
    transcript_path = Path(session.transcript_file or chat_transcript_file(context, session.session_id))
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


def chat_payload(
    context: ProjectContext,
    *,
    session_id: str = "",
    activate: bool = False,
    message_limit: int = 80,
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
    messages = [
        entry.to_dict()
        for entry in load_chat_messages(context, active_session_id, limit=message_limit)
    ] if active_session else []
    summary_text = read_text(Path(active_session.summary_file)) if active_session and active_session.summary_file else ""
    transcript_file = active_session.transcript_file if active_session else ""
    summary_file = active_session.summary_file if active_session else ""
    return {
        "sessions": [session.to_dict() for session in sessions],
        "active_session_id": active_session_id,
        "active_session": active_session.to_dict() if active_session else None,
        "messages": messages,
        "summary_text": compact_text(summary_text, max_chars=4000),
        "summary_file": summary_file,
        "transcript_file": transcript_file,
        "draft_session": not bool(active_session_id),
    }


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
    session_id: str = "",
    create_new_session: bool = False,
) -> dict[str, Any]:
    cleaned_user_message = str(user_message or "").strip()
    if not cleaned_user_message:
        raise ValueError("message is required.")
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
        mode="conversation",
    )
    prompt = build_conversation_prompt(
        context,
        plan_state=plan_state,
        session=session,
        prior_summary=prior_summary,
        recent_messages=[*prior_messages[-7:], user_entry],
        user_message=cleaned_user_message,
    )
    returncode, assistant_text = _run_conversation_reply(
        context,
        prompt=prompt,
        session_id=session.session_id,
    )
    error = ""
    role = "assistant"
    if returncode != 0 or not assistant_text:
        error = _chat_run_error_message(assistant_text)
        assistant_text = error
        role = "system"
    _save_chat_message(
        context,
        session.session_id,
        role=role,
        text=assistant_text,
        mode="conversation",
        status="failed" if error else "completed",
        metadata={
            "returncode": int(returncode),
        },
    )
    rebuild_chat_session_files(context, session.session_id)
    return {
        "chat": chat_payload(context, session_id=session.session_id, activate=True),
        "error": error,
    }
