from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from time import monotonic, perf_counter, time
from typing import Any, Callable

from .chat_sessions import chat_active_session_file, chat_payload, chat_sessions_registry_file
from .codex_app_server import fetch_codex_backend_snapshot
from .contract_wave import (
    lineage_manifest_summary_payload,
    load_common_requirements_state,
    load_lineage_manifest_payloads,
    load_spine_state,
)
from .errors import ARTIFACT_READ_EXCEPTIONS
from .lru_ttl_cache import LruTtlCache
from .model_constants import DEFAULT_LOCAL_MODEL_PROVIDER
from .model_providers import normalize_local_model_provider, normalize_model_provider, provider_preset
from .models import Checkpoint, ExecutionPlanState, ProjectContext
from .orchestrator import Orchestrator
from .planning import checkpoint_timeline_markdown, execution_plan_svg, reconcile_checkpoint_items_from_blocks, resolve_execution_flow_steps
from .project_snapshot import context_execution_snapshot
from .runtime_insights import build_runtime_insights
from .share import project_share_config_payload, project_share_payload
from .step_models import provider_statuses_payload
from .utils import append_jsonl, compact_text, normalize_workflow_mode, now_utc_iso, read_json, read_jsonl_tail, read_last_jsonl, read_text, write_json, write_text_if_changed
from .workspace import LOCAL_PROJECT_LOG_DIRNAME


DETAIL_CACHE_VERSION = 19
LIST_ITEM_CACHE_VERSION = 2
WORKSPACE_LISTING_CACHE_VERSION = 2
PROJECT_TREE_EXCLUDED_NAMES = frozenset({".git", LOCAL_PROJECT_LOG_DIRNAME, "ui_bridge_perf.jsonl"})
_DETAIL_BASE_PAYLOAD_MEMORY_CACHE = LruTtlCache[str, tuple[int, str, dict[str, Any]]](max_entries=48)
_LIST_ITEM_PAYLOAD_MEMORY_CACHE = LruTtlCache[str, tuple[int, str, dict[str, Any]]](max_entries=256)
_WORKSPACE_LISTING_MEMORY_CACHE = LruTtlCache[str, tuple[int, str, dict[str, Any]]](max_entries=16)
_PROVIDER_STATUSES_FETCH_CACHE: tuple[float, dict[str, dict[str, Any]]] | None = None
_PROVIDER_STATUSES_FETCH_CACHE_TTL_SECONDS = 10.0
_DETAIL_CONTENT_SIGNATURE_MEMORY_CACHE: dict[str, tuple[str, str, str, float]] = {}
_DETAIL_CONTENT_SIGNATURE_RECENT_WINDOW_SECONDS = 1.0
_SECTION_PAYLOAD_MEMORY_CACHE = LruTtlCache[str, tuple[str, dict[str, Any]]](max_entries=64)

PLANNING_STAGE_DEFINITIONS = (
    {"key": "context_scan", "label": "Scan repository context"},
    {"key": "planner_a", "label": "Planner Agent A"},
    {"key": "planner_b", "label": "Planner Agent B"},
    {"key": "finalize", "label": "Validate and save plan"},
)


@dataclass(slots=True)
class DetailLogSnapshot:
    ui_events: list[dict[str, Any]]
    blocks: list[dict[str, Any]]
    passes: list[dict[str, Any]]
    test_runs: list[dict[str, Any]]
    latest_block: dict[str, Any]
    latest_pass: dict[str, Any]
    run_control_json: Any
    loop_state_json: Any


def _path_signature(path: Path) -> str:
    if not path.exists():
        return f"{path.name}:missing"
    try:
        stat = path.stat()
    except OSError:
        return f"{path.name}:unavailable"
    kind = "dir" if path.is_dir() else "file"
    return f"{path.name}:{kind}:{stat.st_size}:{stat.st_mtime_ns}"


def _normalize_execution_family_token(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return "idle"
    if normalized in {"syncing", "inconsistent", "stale"}:
        return "syncing"
    if normalized in {"debugging", "running:debugging", "running:parallel-debugging"}:
        return "debugging"
    if normalized == "running:merging":
        return "merging"
    if normalized == "running:closeout":
        return "closeout"
    if normalized == "running:generate-plan":
        return "planning"
    if normalized == "queued" or normalized.startswith("queued:"):
        return "queued"
    if normalized in {"awaiting_review", "awaiting_checkpoint_approval", "checkpoint"}:
        return "checkpoint"
    if normalized in {"completed", "closed_out", "plan_completed"}:
        return "completed"
    if "failed" in normalized:
        return "failed"
    if normalized == "running" or normalized.startswith("running:"):
        return "running"
    if normalized in {"ready", "plan_ready", "setup_ready", "idle"}:
        return "idle"
    return normalized


def _format_execution_consistency_line(name: str, family: str, raw: str = "") -> str:
    normalized_family = _normalize_execution_family_token(family)
    raw_text = str(raw or "").strip()
    if raw_text and raw_text != normalized_family:
        return f"{name}: {normalized_family} ({raw_text})"
    return f"{name}: {normalized_family}"


def build_execution_state_payload(
    project_status: str,
    *,
    display_status: str | None = None,
    planning_running: bool = False,
    loop_state: dict[str, Any] | None = None,
    checkpoints: dict[str, Any] | None = None,
    execution_processes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    loop_state_payload = loop_state if isinstance(loop_state, dict) else {}
    checkpoints_payload = checkpoints if isinstance(checkpoints, dict) else {}
    processes = execution_processes if isinstance(execution_processes, list) else []
    normalized_project_status = str(project_status or "").strip().lower()
    normalized_display_status = str(display_status or project_status or "idle").strip().lower() or "idle"
    raw_project_family = _normalize_execution_family_token(normalized_project_status)
    display_family = _normalize_execution_family_token(normalized_display_status)
    pending_checkpoint = checkpoints_payload.get("pending") if isinstance(checkpoints_payload.get("pending"), dict) else None
    current_checkpoint_id = str(
        loop_state_payload.get("current_checkpoint_id")
        or checkpoints_payload.get("current_checkpoint_id")
        or (pending_checkpoint or {}).get("checkpoint_id")
        or ""
    ).strip()
    current_checkpoint_lineage_id = str(
        loop_state_payload.get("current_checkpoint_lineage_id")
        or checkpoints_payload.get("current_checkpoint_lineage_id")
        or (pending_checkpoint or {}).get("lineage_id")
        or ""
    ).strip()
    pending_checkpoint_approval = bool(loop_state_payload.get("pending_checkpoint_approval")) or normalized_display_status in {
        "awaiting_checkpoint_approval",
        "awaiting_review",
    }

    if pending_checkpoint_approval:
        checkpoint_family = "checkpoint"
        checkpoint_raw = str((pending_checkpoint or {}).get("status") or "awaiting_checkpoint_approval").strip().lower()
    elif processes and (current_checkpoint_id or current_checkpoint_lineage_id):
        checkpoint_family = "running"
        checkpoint_raw = current_checkpoint_id or current_checkpoint_lineage_id
    else:
        checkpoint_items = [
            item
            for item in (checkpoints_payload.get("items", []) if isinstance(checkpoints_payload.get("items"), list) else [])
            if isinstance(item, dict)
        ]
        checkpoint_statuses = [str(item.get("status", "")).strip().lower() for item in checkpoint_items]
        checkpoint_raw = ""
        if checkpoint_items and checkpoint_statuses and all(status in {"approved", "completed"} for status in checkpoint_statuses):
            checkpoint_family = "completed"
        elif any("failed" in status for status in checkpoint_statuses):
            checkpoint_family = "failed"
        else:
            checkpoint_family = "idle"

    if normalized_display_status.startswith("queued:"):
        process_family = "queued"
    elif normalized_display_status in {"running:generate-plan", "running:closeout", "running:debugging", "running:parallel-debugging", "running:merging"}:
        process_family = display_family
    elif normalized_display_status == "running" or normalized_display_status.startswith("running:"):
        process_family = "running"
    elif processes:
        process_family = "running"
    else:
        process_family = "idle"

    flow_family = "idle"
    if checkpoint_family == "checkpoint":
        flow_family = "checkpoint"
    elif planning_running or normalized_display_status == "running:generate-plan":
        flow_family = "planning"
    elif normalized_display_status == "running:closeout":
        flow_family = "closeout"
    elif normalized_display_status in {"running:debugging", "running:parallel-debugging"}:
        flow_family = "debugging"
    elif normalized_display_status == "running:merging":
        flow_family = "merging"
    elif normalized_display_status.startswith("queued:"):
        flow_family = "queued"
    elif normalized_display_status == "running" or normalized_display_status.startswith("running:"):
        flow_family = "running"
    elif raw_project_family != "idle":
        flow_family = raw_project_family

    toolbar_family = raw_project_family
    if checkpoint_family == "checkpoint":
        toolbar_family = "checkpoint"
    elif planning_running or normalized_display_status == "running:generate-plan":
        toolbar_family = "planning"
    elif normalized_display_status == "running:closeout":
        toolbar_family = "closeout"
    elif normalized_display_status in {"running:debugging", "running:parallel-debugging"}:
        toolbar_family = "debugging"
    elif normalized_display_status == "running:merging":
        toolbar_family = "merging"
    elif process_family != "idle":
        toolbar_family = process_family
    elif flow_family != "idle":
        toolbar_family = flow_family

    surfaces = {
        "toolbar": toolbar_family,
        "flow": flow_family,
        "checkpoint": checkpoint_family,
        "process": process_family,
    }
    active_families: list[str] = []
    for family in (_normalize_execution_family_token(value) for value in surfaces.values()):
        if family == "idle" or family in active_families:
            continue
        active_families.append(family)
    terminal_failure = raw_project_family == "failed" or display_family == "failed"
    consistent = True if terminal_failure else len(active_families) <= 1
    resolved_display_family = "failed" if terminal_failure else (display_family if consistent else "syncing")
    mismatch_entries = [
        _format_execution_consistency_line(name, family)
        for name, family in surfaces.items()
        if _normalize_execution_family_token(family) != "idle"
    ]
    return {
        "display_family": resolved_display_family,
        "display_status": normalized_display_status,
        "project_status": normalized_project_status or normalized_display_status,
        "consistent": consistent,
        "active_families": active_families,
        "checkpoint_family": _normalize_execution_family_token(checkpoint_family),
        "flow_family": _normalize_execution_family_token(flow_family),
        "process_family": _normalize_execution_family_token(process_family),
        "toolbar_family": _normalize_execution_family_token(toolbar_family),
        "mismatch_summary": "" if consistent else " | ".join(mismatch_entries),
        "report_lines": [
            _format_execution_consistency_line("toolbar", toolbar_family, normalized_project_status),
            _format_execution_consistency_line("flow", flow_family, normalized_display_status),
            _format_execution_consistency_line("checkpoint", checkpoint_family, checkpoint_raw),
            _format_execution_consistency_line("process", process_family, normalized_display_status),
        ],
    }


def _json_or_text_signature(path: Path) -> str:
    base_signature = _path_signature(path)
    if not path.exists() or path.is_dir():
        return base_signature
    try:
        payload = read_json(path, default=None)
    except ARTIFACT_READ_EXCEPTIONS:
        try:
            normalized = read_text(path, default="")
        except ARTIFACT_READ_EXCEPTIONS:
            return f"{base_signature}:unavailable"
    else:
        if payload is None:
            try:
                normalized = read_text(path, default="")
            except ARTIFACT_READ_EXCEPTIONS:
                normalized = ""
        else:
            normalized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()
    return f"{base_signature}:{digest}"


def _preview_tree_signature(path: Path, max_entries: int = 16, child_limit: int = 8) -> str:
    return _preview_tree_structure_token(path, max_entries=max_entries, child_limit=child_limit)


def _preview_tree_structure_token(path: Path, max_entries: int = 16, child_limit: int = 8) -> str:
    if not path.exists() or not path.is_dir():
        return f"{path.name}:missing"
    try:
        children = sorted(
            (item for item in path.iterdir() if item.name not in PROJECT_TREE_EXCLUDED_NAMES),
            key=lambda item: (not item.is_dir(), item.name.lower()),
        )
    except OSError:
        return f"{path.name}:unavailable"
    digest = hashlib.sha1()
    digest.update(str(path).encode("utf-8"))
    for child in children[:max_entries]:
        digest.update(str(child.name).encode("utf-8"))
        digest.update(("dir" if child.is_dir() else "file").encode("utf-8"))
        if child.is_dir():
            try:
                grandchildren = sorted(
                    (item for item in child.iterdir() if item.name not in PROJECT_TREE_EXCLUDED_NAMES),
                    key=lambda item: (not item.is_dir(), item.name.lower()),
                )
            except OSError:
                digest.update(b"grandchildren:unavailable")
            else:
                for grandchild in grandchildren[:child_limit]:
                    digest.update(str(grandchild.name).encode("utf-8"))
                    digest.update(("dir" if grandchild.is_dir() else "file").encode("utf-8"))
    digest.update(f"count:{len(children)}".encode("utf-8"))
    return digest.hexdigest()


def _project_share_payload_signature(project: ProjectContext) -> str:
    digest = hashlib.sha1()
    digest.update(_path_signature(project.paths.workspace_root / "share_sessions.json").encode("utf-8"))
    digest.update(_path_signature(project.paths.state_dir / "share_sessions.json").encode("utf-8"))
    digest.update(_path_signature(project.paths.workspace_root / "share_server.json").encode("utf-8"))
    digest.update(_path_signature(project.paths.workspace_root / "public_tunnel.json").encode("utf-8"))
    digest.update(_path_signature(project.paths.workspace_root / "share_server_config.json").encode("utf-8"))
    return digest.hexdigest()


def _normalize_execution_processes(execution_processes: Any) -> list[dict[str, Any]]:
    if not isinstance(execution_processes, list):
        return []
    normalized: list[dict[str, Any]] = []
    for entry in execution_processes:
        if not isinstance(entry, dict):
            continue
        try:
            pid = int(entry.get("pid", 0) or 0)
        except (TypeError, ValueError):
            continue
        if pid <= 0:
            continue
        normalized.append(
            {
                "scope_id": str(entry.get("scope_id", "")).strip(),
                "label": str(entry.get("label", "")).strip(),
                "pid": pid,
            }
        )
    normalized.sort(key=lambda item: (item["pid"], item["label"], item["scope_id"]))
    return normalized


def _clone_cached_list_item_payload(payload: dict[str, Any]) -> dict[str, Any]:
    cloned = dict(payload)
    stats = payload.get("stats")
    if isinstance(stats, dict):
        cloned["stats"] = dict(stats)
    return cloned


def _clone_cached_detail_payload(payload: dict[str, Any]) -> dict[str, Any]:
    cloned = {
        key: (dict(value) if isinstance(value, dict) else value)
        for key, value in payload.items()
    }
    snapshot = payload.get("snapshot")
    if isinstance(snapshot, dict):
        cloned["snapshot"] = {
            key: (dict(value) if isinstance(value, dict) else value)
            for key, value in snapshot.items()
        }
    bottom_panels = payload.get("bottom_panels")
    if isinstance(bottom_panels, dict):
        cloned["bottom_panels"] = {
            key: (dict(value) if isinstance(value, dict) else value)
            for key, value in bottom_panels.items()
        }
    execution_processes = payload.get("execution_processes")
    if isinstance(execution_processes, list):
        cloned["execution_processes"] = [dict(item) if isinstance(item, dict) else item for item in execution_processes]
    return cloned


def _clone_workspace_listing_payload(payload: dict[str, Any]) -> dict[str, Any]:
    projects = payload.get("projects")
    history = payload.get("history")
    workspace = payload.get("workspace")
    return {
        "projects": [dict(item) if isinstance(item, dict) else item for item in projects] if isinstance(projects, list) else [],
        "history": [dict(item) if isinstance(item, dict) else item for item in history] if isinstance(history, list) else [],
        "workspace": dict(workspace) if isinstance(workspace, dict) else {},
    }


def _clone_section_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(payload)


def _section_payload_from_cache(cache_key: str, signature: str) -> dict[str, Any] | None:
    cached = _SECTION_PAYLOAD_MEMORY_CACHE.get(cache_key)
    if cached is None or cached[0] != signature:
        return None
    return _clone_section_payload(cached[1])


def _store_section_payload(cache_key: str, signature: str, payload: dict[str, Any]) -> dict[str, Any]:
    _SECTION_PAYLOAD_MEMORY_CACHE.set(cache_key, (signature, _clone_section_payload(payload)))
    return payload


def project_detail_content_signature(
    project: ProjectContext,
    detail_level: str,
    *,
    execution_processes: Any = None,
) -> str:
    normalized_detail_level = "core" if str(detail_level).strip().lower() == "core" else "full"
    normalized_execution_processes = _normalize_execution_processes(execution_processes)
    cache_key = f"{project.paths.project_root.resolve()}|{normalized_detail_level}"
    lightweight_pre_digest = hashlib.sha1()
    lightweight_pre_digest.update(f"detail-cache-v{DETAIL_CACHE_VERSION}:{normalized_detail_level}".encode("utf-8"))
    lightweight_pre_digest.update(str(project.metadata.current_status).encode("utf-8"))
    lightweight_pre_digest.update(str(project.metadata.last_run_at or "").encode("utf-8"))
    lightweight_pre_digest.update(str(project.metadata.current_safe_revision or "").encode("utf-8"))
    lightweight_pre_digest.update(str(project.loop_state.current_task or "").encode("utf-8"))
    lightweight_pre_digest.update(_json_or_text_signature(project.paths.execution_plan_file).encode("utf-8"))
    lightweight_pre_digest.update(json.dumps(normalized_execution_processes, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    tracked_files = [
        project.paths.metadata_file,
        project.paths.project_config_file,
        project.paths.loop_state_file,
        project.paths.execution_plan_file,
        project.paths.ui_control_file,
        project.paths.block_log_file,
        project.paths.pass_log_file,
        project.paths.logs_dir / "test_runs.jsonl",
        project.paths.ui_event_log_file,
        project.paths.checkpoint_state_file,
        project.paths.spine_file,
        project.paths.common_requirements_file,
        project.paths.contract_wave_audit_file,
        project.paths.ml_mode_state_file,
        chat_sessions_registry_file(project),
        chat_active_session_file(project),
    ]
    if normalized_detail_level == "full":
        tracked_files.extend(
            [
                project.paths.checkpoint_timeline_file,
                project.paths.attempt_history_file,
                project.paths.closeout_report_file,
                project.paths.ml_experiment_report_file,
                project.paths.ml_experiment_results_svg_file,
                project.paths.block_review_file,
                project.paths.state_dir / "share_sessions.json",
                project.paths.workspace_root / "share_server.json",
                project.paths.workspace_root / "public_tunnel.json",
                project.paths.workspace_root / "share_server_config.json",
                project.paths.closeout_report_docx_file,
                project.paths.active_task_file,
                project.paths.mid_term_plan_file,
                project.paths.scope_guard_file,
                project.paths.research_notes_file,
                project.paths.shared_contracts_file,
                project.paths.lineage_manifests_dir,
                project.paths.planning_metrics_file,
            ]
        )
    for path in tracked_files:
        lightweight_pre_digest.update(_path_signature(path).encode("utf-8"))
    lightweight_pre_signature = lightweight_pre_digest.hexdigest()
    cached = _DETAIL_CONTENT_SIGNATURE_MEMORY_CACHE.get(cache_key)
    now_monotonic = monotonic()
    if (
        normalized_detail_level == "full"
        and cached is not None
        and cached[0] == lightweight_pre_signature
        and (now_monotonic - cached[3]) <= _DETAIL_CONTENT_SIGNATURE_RECENT_WINDOW_SECONDS
    ):
        return cached[2]

    tracked_tree_roots: list[Path] = []
    if normalized_detail_level == "full":
        pre_digest = hashlib.sha1()
        pre_digest.update(lightweight_pre_signature.encode("utf-8"))
        tracked_tree_roots = [
            project.paths.repo_dir,
            project.paths.docs_dir,
            project.paths.reports_dir,
            project.paths.state_dir,
            project.paths.logs_dir,
            project.paths.memory_dir,
        ]
        for path in tracked_tree_roots:
            pre_digest.update(_preview_tree_structure_token(path).encode("utf-8"))
        pre_signature = pre_digest.hexdigest()
    else:
        pre_signature = lightweight_pre_signature
    if cached is not None and cached[1] == pre_signature:
        _DETAIL_CONTENT_SIGNATURE_MEMORY_CACHE[cache_key] = (cached[0], cached[1], cached[2], now_monotonic)
        return cached[2]

    digest = hashlib.sha1()
    digest.update(pre_signature.encode("utf-8"))
    if normalized_detail_level == "full":
        digest.update(_project_share_payload_signature(project).encode("utf-8"))
        for path in tracked_tree_roots:
            digest.update(_preview_tree_signature(path).encode("utf-8"))
    signature = digest.hexdigest()
    _DETAIL_CONTENT_SIGNATURE_MEMORY_CACHE[cache_key] = (
        lightweight_pre_signature,
        pre_signature,
        signature,
        now_monotonic,
    )
    return signature


def _detail_cache_file(project: ProjectContext, detail_level: str) -> Path:
    normalized_detail_level = "core" if str(detail_level).strip().lower() == "core" else "full"
    return project.paths.state_dir / f"PROJECT_DETAIL_CACHE_{normalized_detail_level.upper()}.json"


def _detail_signature(content_signature: str, codex_status: dict[str, Any]) -> str:
    digest = hashlib.sha1()
    digest.update(content_signature.encode("utf-8"))
    digest.update(json.dumps(codex_status, sort_keys=True).encode("utf-8"))
    return digest.hexdigest()


def _snapshot_epoch_ms() -> int:
    return int(time() * 1000)


def _snapshot_metadata(
    snapshot_kind: str,
    *,
    source_signature: str,
    source_cursor: dict[str, Any],
    state_origin: str,
    generated_at: str | None = None,
    content_signature: str = "",
    detail_signature: str = "",
) -> dict[str, Any]:
    cursor = deepcopy(source_cursor)
    digest = hashlib.sha1()
    for component in (
        snapshot_kind,
        source_signature,
        content_signature,
        detail_signature,
        state_origin,
    ):
        digest.update(str(component).encode("utf-8"))
    digest.update(json.dumps(cursor, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8"))
    return {
        "snapshot_kind": snapshot_kind,
        "snapshot_id": digest.hexdigest(),
        "snapshot_epoch": _snapshot_epoch_ms(),
        "generated_at": generated_at or now_utc_iso(),
        "state_origin": state_origin,
        "source_signature": source_signature,
        "source_cursor": cursor,
    }


def _persisted_state_source_signature(project: ProjectContext) -> str:
    return "|".join(
        (
            _path_signature(project.paths.metadata_file),
            _path_signature(project.paths.project_config_file),
            _path_signature(project.paths.loop_state_file),
            _path_signature(project.paths.checkpoint_state_file),
            _json_or_text_signature(project.paths.execution_plan_file),
            _path_signature(project.paths.ui_control_file),
        )
    )


def _event_derived_source_signature(project: ProjectContext) -> str:
    return "|".join(
        (
            _path_signature(project.paths.ui_event_log_file),
            _path_signature(project.paths.block_log_file),
            _path_signature(project.paths.pass_log_file),
            _path_signature(project.paths.logs_dir / "test_runs.jsonl"),
        )
    )


def _project_detail_snapshot_sources(
    project: ProjectContext,
    *,
    normalized_detail_level: str,
    content_signature: str,
    codex_status: dict[str, Any],
    generated_at: str | None = None,
) -> dict[str, dict[str, Any]]:
    generated_at = generated_at or now_utc_iso()
    persisted_cursor = {
        "metadata": _path_signature(project.paths.metadata_file),
        "runtime": _path_signature(project.paths.project_config_file),
        "loop_state": _path_signature(project.paths.loop_state_file),
        "checkpoint_state": _path_signature(project.paths.checkpoint_state_file),
        "execution_plan": _json_or_text_signature(project.paths.execution_plan_file),
        "run_control": _path_signature(project.paths.ui_control_file),
    }
    event_cursor = {
        "ui_events": _path_signature(project.paths.ui_event_log_file),
        "blocks": _path_signature(project.paths.block_log_file),
        "passes": _path_signature(project.paths.pass_log_file),
        "test_runs": _path_signature(project.paths.logs_dir / "test_runs.jsonl"),
    }
    live_runtime_cursor = {
        "codex_path": project.runtime.codex_path,
        "refresh_codex_status": bool(codex_status),
        "provider_statuses": (
            str(sorted(codex_status.get("provider_statuses").keys()))
            if isinstance(codex_status, dict) and isinstance(codex_status.get("provider_statuses"), dict)
            else ""
        ),
    }
    cache_view_cursor = {
        "detail_level": normalized_detail_level,
        "project_root": str(project.paths.project_root),
        "repo_id": project.metadata.repo_id,
    }
    return {
        "persisted_state": _snapshot_metadata(
            "persisted_state",
            source_signature=_persisted_state_source_signature(project),
            source_cursor=persisted_cursor,
            state_origin="disk",
            generated_at=generated_at,
            content_signature=content_signature,
        ),
        "event_derived": _snapshot_metadata(
            "event_derived",
            source_signature=_event_derived_source_signature(project),
            source_cursor=event_cursor,
            state_origin="events",
            generated_at=generated_at,
            content_signature=content_signature,
        ),
        "live_runtime": _snapshot_metadata(
            "live_runtime",
            source_signature=hashlib.sha1(json.dumps(codex_status, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
            source_cursor=live_runtime_cursor,
            state_origin="process",
            generated_at=generated_at,
            content_signature=content_signature,
        ),
        "cache_view": _snapshot_metadata(
            "cache_view",
            source_signature=content_signature,
            source_cursor=cache_view_cursor,
            state_origin="cache_view",
            generated_at=generated_at,
            content_signature=content_signature,
            detail_signature=_detail_signature(content_signature, codex_status),
        ),
    }


def _detail_perf_log(project: ProjectContext, event_type: str, details: dict[str, Any]) -> None:
    append_jsonl(
        project.paths.logs_dir / "ui_bridge_perf.jsonl",
        {
            "timestamp": now_utc_iso(),
            "event_type": event_type,
            "repo_id": project.metadata.repo_id,
            "project_dir": str(project.metadata.repo_path),
            "details": details,
        },
    )


def _tail_slice(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    if len(items) <= limit:
        return list(items)
    return list(items[-limit:])


def _latest_entry(items: list[dict[str, Any]]) -> dict[str, Any]:
    if not items:
        return {}
    latest = items[-1]
    return latest if isinstance(latest, dict) else {}


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def build_planning_progress(
    ui_events: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    event_items = ui_events or []
    planning_events: list[dict[str, Any]] = []
    planning_stage_events: list[dict[str, Any]] = []
    stage_labels = {item["key"]: item["label"] for item in PLANNING_STAGE_DEFINITIONS}
    agent_labels: dict[str, str] = {}
    for item in event_items:
        if not isinstance(item, dict):
            continue
        details = item.get("details", {})
        if not isinstance(details, dict):
            continue
        if str(details.get("flow", "")).strip().lower() != "planning":
            continue
        planning_events.append(item)
        stage_key = str(details.get("stage_key", "")).strip().lower()
        if not stage_key:
            continue
        if str(details.get("stage_label", "")).strip():
            stage_labels[stage_key] = str(details.get("stage_label", "")).strip()
        if str(details.get("agent_label", "")).strip():
            agent_labels[stage_key] = str(details.get("agent_label", "")).strip()
    if not planning_events:
        return {}
    latest = planning_events[-1]
    latest_details = latest.get("details", {})
    if not isinstance(latest_details, dict):
        latest_details = {}
    latest_status = str(latest_details.get("status", "")).strip().lower()
    latest_event_type = str(latest.get("event_type", "")).strip().lower()
    if latest_event_type == "plan-stopped" or latest_status in {"stopped", "cancelled", "canceled"}:
        return {}
    planning_stage_events = [
        item
        for item in planning_events
        if str((item.get("details", {}) or {}).get("stage_key", "")).strip()
    ]
    if not planning_stage_events:
        return {}

    latest = planning_stage_events[-1]
    latest_details = latest.get("details", {})
    if not isinstance(latest_details, dict):
        latest_details = {}
    current_stage_key = str(latest_details.get("stage_key", "")).strip().lower()
    stage_count = _positive_int(latest_details.get("stage_count", len(PLANNING_STAGE_DEFINITIONS)), len(PLANNING_STAGE_DEFINITIONS))
    current_stage_index = _positive_int(latest_details.get("stage_index", 1), 1)
    current_stage_index = min(stage_count, current_stage_index)
    current_status = str(latest_details.get("status", "running")).strip().lower() or "running"
    if current_status not in {"running", "completed", "failed"}:
        current_status = "running"

    ordered_keys = [item["key"] for item in PLANNING_STAGE_DEFINITIONS]
    for event in planning_events:
        details = event.get("details", {})
        if not isinstance(details, dict):
            continue
        stage_key = str(details.get("stage_key", "")).strip().lower()
        if stage_key and stage_key not in ordered_keys:
            ordered_keys.append(stage_key)

    stages: list[dict[str, Any]] = []
    for index, stage_key in enumerate(ordered_keys[:stage_count], start=1):
        if index < current_stage_index:
            stage_status = "completed"
        elif index == current_stage_index:
            stage_status = current_status
        else:
            stage_status = "pending"
        stage_label = stage_labels.get(stage_key) or stage_key.replace("_", " ").title()
        stage_payload = {
            "key": stage_key,
            "index": index,
            "label": stage_label,
            "status": stage_status,
        }
        agent_label = agent_labels.get(stage_key, "")
        if agent_label:
            stage_payload["agent_label"] = agent_label
        stages.append(stage_payload)

    if current_status == "completed":
        completed_stages = current_stage_index
        progress_units = float(current_stage_index)
    elif current_status == "failed":
        completed_stages = max(0, current_stage_index - 1)
        progress_units = max(0.0, current_stage_index - 0.5)
    else:
        completed_stages = max(0, current_stage_index - 1)
        progress_units = max(0.0, current_stage_index - 0.5)
    percent = int(round((progress_units / stage_count) * 100)) if stage_count else 0
    percent = max(0, min(100, percent))
    current_stage = next((item for item in stages if item["index"] == current_stage_index), {})

    return {
        "stage_count": stage_count,
        "completed_stages": completed_stages,
        "percent": percent,
        "current_stage_key": current_stage_key,
        "current_stage_index": current_stage_index,
        "current_stage_label": current_stage.get("label", ""),
        "current_stage_status": current_status,
        "current_agent_label": current_stage.get("agent_label", ""),
        "message": str(latest.get("message", "")).strip(),
        "event_type": str(latest.get("event_type", "")).strip(),
        "stages": stages,
    }


def progress_caption(plan_state: ExecutionPlanState) -> str:
    completed = len([step for step in plan_state.steps if step.status == "completed"])
    total = len(plan_state.steps)
    if total == 0:
        return "No plan yet"
    if completed == total:
        if plan_state.closeout_status == "completed":
            return f"Completed {completed}/{total} steps, closeout completed"
        if plan_state.closeout_status == "running":
            return f"Completed {completed}/{total} steps, closeout running"
        if plan_state.closeout_status == "failed":
            return f"Completed {completed}/{total} steps, closeout failed"
        return f"Completed {completed}/{total} steps, closeout pending"
    uses_dag = (
        str(plan_state.execution_mode).strip().lower() == "parallel"
        and any(step.depends_on or step.owned_paths for step in plan_state.steps)
    )
    if uses_dag:
        running = [step.step_id for step in plan_state.steps if step.status == "running"]
        integrating = [step.step_id for step in plan_state.steps if step.status == "integrating"]
        if running or integrating:
            parts: list[str] = []
            if running:
                parts.append(f"running: {', '.join(running)}")
            if integrating:
                parts.append(f"integrating: {', '.join(integrating)}")
            return f"Completed {completed}/{total} steps, {'; '.join(parts)}"
        completed_ids = {step.step_id for step in plan_state.steps if step.status == "completed"}
        ready = [
            step.step_id
            for step in plan_state.steps
            if step.status != "completed"
            and all(dependency in completed_ids for dependency in step.depends_on)
        ]
        return f"Completed {completed}/{total} steps, pending: {', '.join(ready) if ready else 'blocked'}"
    next_step = next((step.step_id for step in plan_state.steps if step.status != "completed"), "done")
    return f"Completed {completed}/{total} steps, next: {next_step}"


def _execution_step_label(step: Any) -> str:
    if step is None:
        return ""
    step_id = str(getattr(step, "step_id", "")).strip()
    title = str(getattr(step, "title", "")).strip()
    return " ".join(part for part in (step_id, title) if part).strip()


def project_progress_payload(plan_state: ExecutionPlanState) -> dict[str, Any]:
    steps = list(plan_state.steps)
    total = len(steps)
    completed = len([step for step in steps if step.status == "completed"])
    failed_steps = [step for step in steps if step.status == "failed"]
    running_steps = [step for step in steps if step.status in {"running", "integrating"}]
    pending_steps = [step for step in steps if step.status != "completed"]
    closeout_status = str(plan_state.closeout_status or "").strip().lower()
    current_step = running_steps[0] if running_steps else failed_steps[0] if failed_steps else pending_steps[0] if pending_steps else None
    current_step_id = str(getattr(current_step, "step_id", "")).strip()
    current_step_label = _execution_step_label(current_step)
    current_step_deadline = str(getattr(current_step, "deadline_at", "")).strip()
    if closeout_status == "running" or (completed == total and total > 0 and closeout_status not in {"completed", "failed"}):
        current_step_id = "CLOSEOUT"
        current_step_label = str(plan_state.closeout_title or "Closeout").strip() or "Closeout"
        current_step_deadline = str(plan_state.closeout_deadline_at or "").strip()
    percent = int(round((completed / total) * 100)) if total else (100 if closeout_status == "completed" else 0)
    return {
        "caption": progress_caption(plan_state),
        "percent": percent if total or closeout_status == "completed" else None,
        "completed": completed,
        "total": total,
        "running": len(running_steps),
        "failed": len(failed_steps),
        "currentStep": current_step_label,
        "current_step": current_step_label,
        "current_step_id": current_step_id,
        "deadline_at": current_step_deadline,
        "estimatedRemaining": None,
        "estimated_remaining": None,
    }


def project_summary(
    orchestrator: Orchestrator,
    project: ProjectContext,
    plan_state: ExecutionPlanState | None = None,
    *,
    current_status: str | None = None,
    recent_blocks: list[dict[str, Any]] | None = None,
) -> str:
    plan = plan_state or orchestrator.load_execution_plan_state(project)
    remaining = [step.step_id for step in plan.steps if step.status != "completed"]
    blocks = recent_blocks if recent_blocks is not None else read_jsonl_tail(project.paths.block_log_file, 5)
    recent_statuses = [str(item.get("status", "")) for item in blocks][-3:]
    runtime_provider = normalize_model_provider(str(getattr(project.runtime, "model_provider", "openai") or "openai").strip())
    local_provider = normalize_local_model_provider(str(getattr(project.runtime, "local_model_provider", "") or "").strip())
    preset = provider_preset(runtime_provider)
    if runtime_provider == "oss" and local_provider == DEFAULT_LOCAL_MODEL_PROVIDER:
        provider_summary = provider_preset("ollama").display_name
    elif runtime_provider == "oss":
        provider_summary = f"{preset.display_name}/{local_provider or 'oss'}"
    else:
        provider_summary = preset.display_name
    runtime_model = str(getattr(project.runtime, "execution_model", "") or getattr(project.runtime, "model", "") or "").strip()
    lines = [
        f"Name: {project.metadata.display_name or project.metadata.slug}",
        f"Directory: {project.metadata.repo_path}",
        f"GitHub: {project.metadata.origin_url or 'Not connected'}",
        f"Branch: {project.metadata.branch}",
        f"Status: {current_status or project.metadata.current_status}",
        f"Workflow: {normalize_workflow_mode(getattr(plan, 'workflow_mode', '') or getattr(project.runtime, 'workflow_mode', 'standard'))}",
        f"Model: {runtime_model}  ({project.runtime.effort}) [{provider_summary}]",
        f"Verification: {plan.default_test_command or project.runtime.test_cmd}",
        f"Remaining Steps: {', '.join(remaining) if remaining else 'None'}",
        f"Closeout: {plan.closeout_status}",
    ]
    if plan.plan_title.strip():
        lines.append(f"Plan Title: {plan.plan_title.strip()}")
    if project.metadata.archived_at:
        lines.append(f"Archived At: {project.metadata.archived_at}")
    if project.metadata.last_run_at:
        lines.append(f"Last Run: {project.metadata.last_run_at}")
    if getattr(project.runtime, "generate_word_report", False) and project.paths.closeout_report_docx_file.exists():
        lines.append(f"Word Report: {project.paths.closeout_report_docx_file}")
    if recent_statuses:
        lines.append(f"Recent Blocks: {', '.join(recent_statuses)}")
    return "\n".join(lines)


def project_stats(plan_state: ExecutionPlanState) -> dict[str, Any]:
    completed = len([step for step in plan_state.steps if step.status == "completed"])
    failed = len([step for step in plan_state.steps if step.status == "failed"])
    running = len([step for step in plan_state.steps if step.status in {"running", "integrating"}])
    return {
        "total_steps": len(plan_state.steps),
        "completed_steps": completed,
        "failed_steps": failed,
        "running_steps": running,
        "remaining_steps": max(0, len(plan_state.steps) - completed),
    }


def workspace_snapshot(statuses: list[str]) -> dict[str, Any]:
    running = 0
    ready = 0
    failed = 0
    for status in statuses:
        if status.startswith("running:"):
            running += 1
        elif status in {"setup_ready", "plan_ready", "plan_completed", "closed_out", "ready"}:
            ready += 1
        elif status.endswith("failed") or status in {"failed", "closeout_failed"}:
            failed += 1
    return {
        "project_count": len(statuses),
        "ready_like": ready,
        "running": running,
        "failed": failed,
    }


def safe_json(path: Path, default: Any = None) -> Any:
    try:
        return read_json(path, default=default)
    except ARTIFACT_READ_EXCEPTIONS:
        return default


def safe_text(path: Path, default: str = "") -> str:
    try:
        return read_text(path, default=default)
    except ARTIFACT_READ_EXCEPTIONS:
        return default


def preview_text(path: Path, default: str = "", max_chars: int = 12_000) -> str:
    return compact_text(safe_text(path, default=default), max_chars=max_chars)


def preview_tree(path: Path, max_entries: int = 16) -> list[dict[str, Any]]:
    if not path.exists() or not path.is_dir():
        return []
    try:
        children = sorted(
            (item for item in path.iterdir() if item.name not in PROJECT_TREE_EXCLUDED_NAMES),
            key=lambda item: (not item.is_dir(), item.name.lower()),
        )
    except OSError:
        return [{"label": "Directory unavailable", "path": str(path), "kind": "meta"}]
    entries: list[dict[str, Any]] = []
    for child in children[:max_entries]:
        item = {
            "label": child.name,
            "path": str(child),
            "kind": "dir" if child.is_dir() else "file",
        }
        if child.is_dir():
            try:
                grandchildren = sorted(
                    (entry for entry in child.iterdir() if entry.name not in PROJECT_TREE_EXCLUDED_NAMES),
                    key=lambda entry: (not entry.is_dir(), entry.name.lower()),
                )
            except OSError:
                item["children"] = [{"label": "Directory unavailable", "path": str(child), "kind": "meta"}]
            else:
                item["children"] = [
                    {
                        "label": grandchild.name,
                        "path": str(grandchild),
                        "kind": "dir" if grandchild.is_dir() else "file",
                    }
                    for grandchild in grandchildren[:8]
                ]
        entries.append(item)
    if len(children) > max_entries:
        entries.append({"label": f"+{len(children) - max_entries} more", "path": str(path), "kind": "meta"})
    return entries


def _planning_metric_entries(path: Path, limit: int = 80) -> list[dict[str, Any]]:
    entries = read_jsonl_tail(path, limit)
    normalized: list[dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        stage = str(item.get("stage", "")).strip()
        if not stage:
            continue
        flow = str(item.get("flow", "")).strip() or "planning"
        try:
            duration_ms = float(item.get("duration_ms", 0.0) or 0.0)
        except (TypeError, ValueError):
            duration_ms = 0.0
        normalized.append(
            {
                "generated_at": str(item.get("generated_at", "")).strip(),
                "flow": flow,
                "stage": stage,
                "duration_ms": round(duration_ms, 3),
                "block_index": item.get("block_index"),
                "repo_id": str(item.get("repo_id", "")).strip(),
                "repo_slug": str(item.get("repo_slug", "")).strip(),
            }
        )
    return normalized


def _planning_metrics_report_payload(context: ProjectContext) -> dict[str, Any]:
    entries = _planning_metric_entries(context.paths.planning_metrics_file)
    if not entries:
        return {
            "path": str(context.paths.planning_metrics_file),
            "entry_count": 0,
            "recent_items": [],
            "stage_summary": [],
            "slowest_item": None,
            "latest_generated_at": "",
        }
    recent_items = list(reversed(entries[-16:]))
    summary_index: dict[tuple[str, str], dict[str, Any]] = {}
    for item in entries:
        key = (str(item.get("flow", "")).strip(), str(item.get("stage", "")).strip())
        bucket = summary_index.setdefault(
            key,
            {
                "flow": key[0],
                "stage": key[1],
                "count": 0,
                "total_ms": 0.0,
                "max_ms": 0.0,
            },
        )
        duration_ms = float(item.get("duration_ms", 0.0) or 0.0)
        bucket["count"] += 1
        bucket["total_ms"] += duration_ms
        bucket["max_ms"] = max(float(bucket["max_ms"]), duration_ms)
    stage_summary = sorted(
        (
            {
                **bucket,
                "avg_ms": round(float(bucket["total_ms"]) / max(1, int(bucket["count"])), 3),
                "total_ms": round(float(bucket["total_ms"]), 3),
                "max_ms": round(float(bucket["max_ms"]), 3),
            }
            for bucket in summary_index.values()
        ),
        key=lambda item: (float(item["total_ms"]), float(item["max_ms"])),
        reverse=True,
    )[:10]
    slowest_item = max(entries, key=lambda item: float(item.get("duration_ms", 0.0) or 0.0))
    return {
        "path": str(context.paths.planning_metrics_file),
        "entry_count": len(entries),
        "recent_items": recent_items,
        "stage_summary": stage_summary,
        "slowest_item": slowest_item,
        "latest_generated_at": str(recent_items[0].get("generated_at", "")).strip() if recent_items else "",
    }


def _flow_svg_signature(context: ProjectContext, plan_state: ExecutionPlanState) -> str:
    payload = {
        "title": plan_state.plan_title.strip() or context.metadata.display_name or context.metadata.slug,
        "execution_mode": str(plan_state.execution_mode or "").strip(),
        "closeout_status": str(plan_state.closeout_status or "").strip(),
        "block_log_signature": _json_or_text_signature(context.paths.block_log_file),
        "steps": [],
    }
    for step in plan_state.steps:
        step_payload = step.to_dict()
        for transient_key in ("started_at", "completed_at", "commit_hash", "notes"):
            step_payload.pop(transient_key, None)
        payload["steps"].append(step_payload)
    return hashlib.sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _load_execution_plan_state_for_flow(context: ProjectContext) -> ExecutionPlanState:
    payload = safe_json(context.paths.execution_plan_file, default=None)
    if isinstance(payload, dict):
        try:
            return ExecutionPlanState.from_dict(payload)
        except (TypeError, ValueError, KeyError):
            pass
    return ExecutionPlanState(default_test_command=str(context.runtime.test_cmd or "").strip())


def _flow_svg_payload(context: ProjectContext) -> dict[str, Any]:
    plan_state = _load_execution_plan_state_for_flow(context)
    signature = _flow_svg_signature(context, plan_state)
    marker = f"execution-flow-signature:{signature}"
    flow_svg_text = safe_text(context.paths.execution_flow_svg_file, default="")
    if marker not in flow_svg_text:
        flow_title = plan_state.plan_title.strip() or context.metadata.display_name or context.metadata.slug
        block_entries = read_jsonl_tail(context.paths.block_log_file, 120)
        flow_steps = resolve_execution_flow_steps(plan_state.steps, block_entries)
        rendered = f"<!-- {marker} -->\n{execution_plan_svg(f'{flow_title} execution flow', flow_steps, plan_state.execution_mode)}"
        write_text_if_changed(context.paths.execution_flow_svg_file, rendered)
        flow_svg_text = safe_text(context.paths.execution_flow_svg_file, default=rendered)
    return {
        "flow_svg_path": str(context.paths.execution_flow_svg_file),
        "flow_svg_text": flow_svg_text,
    }


def managed_workspace_tree(context: ProjectContext) -> list[dict[str, Any]]:
    cache_key = f"workspace-tree|{context.metadata.repo_id}"
    signature = "|".join(
        (
            _preview_tree_signature(context.paths.repo_dir),
            str(context.metadata.display_name or context.metadata.slug or context.paths.repo_dir.name),
        )
    )
    cached = _section_payload_from_cache(cache_key, signature)
    if cached is not None:
        return cached.get("workspace_tree", [])
    payload = {
        "workspace_tree": [
            {
                "label": context.paths.repo_dir.name or context.metadata.display_name or context.metadata.slug or "Project",
                "path": str(context.paths.repo_dir),
                "kind": "dir",
                "children": preview_tree(context.paths.repo_dir),
            }
        ]
    }
    return _store_section_payload(cache_key, signature, payload)["workspace_tree"]


def _sort_payload_items(items: list[dict[str, Any]], *timestamp_keys: str) -> list[dict[str, Any]]:
    def sort_key(item: dict[str, Any]) -> str:
        for key in timestamp_keys:
            value = str(item.get(key, "")).strip()
            if value:
                return value
        return ""

    return sorted(items, key=sort_key, reverse=True)


def _contract_wave_report_payload(context: ProjectContext) -> dict[str, Any]:
    spine_state = load_spine_state(context.paths.spine_file)
    common_requirements_state = load_common_requirements_state(context.paths.common_requirements_file)
    spine_history = _sort_payload_items(
        [item.to_dict() for item in spine_state.history],
        "created_at",
    )
    open_requirements = _sort_payload_items(
        [item.to_dict() for item in common_requirements_state.open_requirements],
        "created_at",
    )
    resolved_requirements = _sort_payload_items(
        [item.to_dict() for item in common_requirements_state.resolved_requirements],
        "resolved_at",
        "created_at",
    )
    lineage_manifests = load_lineage_manifest_payloads(context.paths, limit=12, newest_first=True)
    audit_entries = _sort_payload_items(
        read_jsonl_tail(context.paths.contract_wave_audit_file, 20),
        "timestamp",
    )
    manifest_summary = lineage_manifest_summary_payload(context.paths)
    spine_json_text = compact_text(
        json.dumps(spine_state.to_dict(), indent=2, ensure_ascii=False),
        4000,
    )
    common_requirements_json_text = compact_text(
        json.dumps(common_requirements_state.to_dict(), indent=2, ensure_ascii=False),
        4000,
    )

    return {
        "spine": {
            "current_version": spine_state.current_version,
            "updated_at": spine_state.updated_at,
            "history_count": len(spine_state.history),
            "latest_checkpoint": spine_history[0] if spine_history else None,
            "recent_history": spine_history[:8],
            "json_text": spine_json_text or "{\n}\n",
            "path": str(context.paths.spine_file),
        },
        "common_requirements": {
            "updated_at": common_requirements_state.updated_at,
            "open_count": len(common_requirements_state.open_requirements),
            "resolved_count": len(common_requirements_state.resolved_requirements),
            "open_items": open_requirements[:8],
            "resolved_items": resolved_requirements[:8],
            "json_text": common_requirements_json_text or "{\n}\n",
            "path": str(context.paths.common_requirements_file),
        },
        "contract_wave_audit": {
            "recent_items": audit_entries[:12],
            "path": str(context.paths.contract_wave_audit_file),
            "jsonl_text": preview_text(context.paths.contract_wave_audit_file, default="", max_chars=4000),
        },
        "shared_contracts_text": preview_text(
            context.paths.shared_contracts_file,
            default="# Shared Contracts\n\nNo shared contracts recorded yet.\n",
            max_chars=8000,
        ),
        "shared_contracts_path": str(context.paths.shared_contracts_file),
        "lineage_manifests": lineage_manifests[:12],
        "lineage_manifest_summary": manifest_summary,
        "lineage_manifests_dir": str(context.paths.lineage_manifests_dir),
    }


def _latest_failure_details(context: ProjectContext) -> dict[str, Any]:
    latest_failure_status = safe_json(context.paths.reports_dir / "latest_pr_failure_status.json", default={})
    if not isinstance(latest_failure_status, dict) or not latest_failure_status:
        return {}
    report_json_file = str(latest_failure_status.get("report_json_file", "")).strip()
    report_markdown_file = str(latest_failure_status.get("report_markdown_file", "")).strip()
    bundle_json = safe_json(Path(report_json_file), default={}) if report_json_file else {}
    block_index = bundle_json.get("block_index") if isinstance(bundle_json, dict) else None
    block_dir = (
        context.paths.logs_dir / f"block_{int(block_index):04d}"
        if isinstance(block_index, int) and block_index >= 0
        else None
    )
    artifact_files = bundle_json.get("artifact_files", []) if isinstance(bundle_json, dict) else []
    artifact_files = artifact_files if isinstance(artifact_files, list) else []
    if not artifact_files and block_dir is not None and block_dir.exists():
        try:
            artifact_files = [
                str(path)
                for path in sorted(block_dir.iterdir(), key=lambda item: item.name.lower())
                if path.is_file()
            ]
        except OSError:
            artifact_files = []
    return {
        "generated_at": str(latest_failure_status.get("generated_at", "")).strip(),
        "failure_type": str(latest_failure_status.get("failure_type", "")).strip(),
        "posted": bool(latest_failure_status.get("posted")),
        "result": latest_failure_status.get("result", {}) if isinstance(latest_failure_status.get("result"), dict) else {},
        "summary": str(bundle_json.get("summary", "")).strip() if isinstance(bundle_json, dict) else "",
        "selected_task": str(bundle_json.get("selected_task", "")).strip() if isinstance(bundle_json, dict) else "",
        "report_json_file": report_json_file,
        "report_markdown_file": report_markdown_file,
        "report_markdown_text": preview_text(Path(report_markdown_file), default="", max_chars=4000) if report_markdown_file else "",
        "block_index": block_index if isinstance(block_index, int) else None,
        "block_dir": str(block_dir) if block_dir is not None else "",
        "artifact_files": artifact_files,
        "artifacts": bundle_json.get("artifacts", []) if isinstance(bundle_json, dict) and isinstance(bundle_json.get("artifacts", []), list) else [],
    }


def report_payload(context: ProjectContext) -> dict[str, Any]:
    cache_key = f"reports|{context.metadata.repo_id}"
    signature = "|".join(
        (
            _path_signature(context.paths.closeout_report_file),
            _path_signature(context.paths.ml_experiment_report_file),
            _path_signature(context.paths.attempt_history_file),
            _path_signature(context.paths.closeout_report_docx_file),
            _path_signature(context.paths.closeout_report_pptx_file),
            _path_signature(context.paths.ml_experiment_results_svg_file),
            _path_signature(context.paths.spine_file),
            _path_signature(context.paths.common_requirements_file),
            _path_signature(context.paths.contract_wave_audit_file),
            _path_signature(context.paths.lineage_manifests_dir),
            _path_signature(context.paths.planning_metrics_file),
            _path_signature(context.paths.reports_dir / "latest_pr_failure_status.json"),
        )
    )
    cached = _section_payload_from_cache(cache_key, signature)
    if cached is not None:
        return cached
    payload = {
        "closeout_report_text": preview_text(
            context.paths.closeout_report_file,
            default="# Closeout Report\n\nNo closeout has been run yet.\n",
        ),
        "closeout_report_file": str(context.paths.closeout_report_file),
        "ml_experiment_report_text": preview_text(
            context.paths.ml_experiment_report_file,
            default="# ML Experiment Report\n\nNo ML experiment summary has been generated yet.\n",
        ),
        "attempt_history_text": preview_text(context.paths.attempt_history_file, default="No attempt history recorded yet.\n"),
        "word_report_enabled": bool(context.runtime.generate_word_report),
        "word_report_path": (
            str(context.paths.closeout_report_docx_file)
            if context.runtime.generate_word_report and context.paths.closeout_report_docx_file.exists()
            else ""
        ),
        "powerpoint_report_path": str(context.paths.closeout_report_pptx_file) if context.paths.closeout_report_pptx_file.exists() else "",
        "powerpoint_report_target_path": str(context.paths.closeout_report_pptx_file),
        "ml_results_svg_path": str(context.paths.ml_experiment_results_svg_file) if context.paths.ml_experiment_results_svg_file.exists() else "",
        "planning_metrics": _planning_metrics_report_payload(context),
        **_contract_wave_report_payload(context),
        "latest_failure": _latest_failure_details(context),
    }
    return _store_section_payload(cache_key, signature, payload)


def latest_failure_payload(context: ProjectContext) -> dict[str, Any]:
    return _latest_failure_details(context)

def history_payload(context: ProjectContext) -> dict[str, Any]:
    cache_key = f"history|{context.metadata.repo_id}"
    signature = "|".join(
        (
            _path_signature(context.paths.ui_event_log_file),
            _path_signature(context.paths.block_log_file),
            _path_signature(context.paths.pass_log_file),
            _path_signature(context.paths.logs_dir / "test_runs.jsonl"),
            _json_or_text_signature(context.paths.execution_plan_file),
        )
    )
    cached = _section_payload_from_cache(cache_key, signature)
    if cached is not None:
        return cached
    payload = {
        "ui_events": read_jsonl_tail(context.paths.ui_event_log_file, 40),
        "blocks": read_jsonl_tail(context.paths.block_log_file, 20),
        "passes": read_jsonl_tail(context.paths.pass_log_file, 30),
        "test_runs": read_jsonl_tail(context.paths.logs_dir / "test_runs.jsonl", 20),
        **_flow_svg_payload(context),
    }
    payload.update(
        _snapshot_metadata(
            "event_derived",
            source_signature=_event_derived_source_signature(context),
            source_cursor={
                "ui_events": _path_signature(context.paths.ui_event_log_file),
                "blocks": _path_signature(context.paths.block_log_file),
                "passes": _path_signature(context.paths.pass_log_file),
                "test_runs": _path_signature(context.paths.logs_dir / "test_runs.jsonl"),
            },
            state_origin="events",
        )
    )
    return _store_section_payload(cache_key, signature, payload)


def history_payload_from_snapshot(context: ProjectContext, snapshot: DetailLogSnapshot) -> dict[str, Any]:
    payload = {
        "ui_events": list(snapshot.ui_events),
        "blocks": list(snapshot.blocks),
        "passes": list(snapshot.passes),
        "test_runs": list(snapshot.test_runs),
        **_flow_svg_payload(context),
    }
    payload.update(
        _snapshot_metadata(
            "event_derived",
            source_signature=_event_derived_source_signature(context),
            source_cursor={
                "ui_events": len(snapshot.ui_events),
                "blocks": len(snapshot.blocks),
                "passes": len(snapshot.passes),
                "test_runs": len(snapshot.test_runs),
            },
            state_origin="events",
        )
    )
    return payload


def checkpoint_payload(context: ProjectContext) -> dict[str, Any]:
    raw = safe_json(context.paths.checkpoint_state_file, default={"checkpoints": []})
    raw_items = raw.get("checkpoints", []) if isinstance(raw, dict) else []
    block_entries = read_jsonl_tail(context.paths.block_log_file, 240)
    return checkpoint_payload_from_blocks(context, raw_items, block_entries)


def checkpoint_payload_from_blocks(
    context: ProjectContext,
    raw_items: list[dict[str, Any]] | list[Any],
    block_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    waiting_for_approval = bool(context.loop_state.pending_checkpoint_approval)
    active_checkpoint_id = str(context.loop_state.current_checkpoint_id or "").strip()
    active_checkpoint_lineage_id = str(context.loop_state.current_checkpoint_lineage_id or "").strip()
    reconciled_items, _ = reconcile_checkpoint_items_from_blocks(
        raw_items if isinstance(raw_items, list) else [],
        block_entries,
    )
    checkpoints: list[dict[str, Any]] = []
    for item in reconciled_items:
        if not isinstance(item, dict):
            continue
        normalized = deepcopy(item)
        normalized["deadline_at"] = str(normalized.get("deadline_at", "")).strip()
        is_active_checkpoint = bool(active_checkpoint_id) and str(normalized.get("checkpoint_id", "")).strip() == active_checkpoint_id
        if active_checkpoint_lineage_id:
            is_active_checkpoint = is_active_checkpoint and (
                not str(normalized.get("lineage_id", "")).strip()
                or str(normalized.get("lineage_id", "")).strip() == active_checkpoint_lineage_id
            )
        if waiting_for_approval and is_active_checkpoint and normalized.get("status") != "awaiting_review":
            normalized["status"] = "awaiting_review"
        elif normalized.get("status") == "awaiting_review" and not waiting_for_approval:
            normalized["status"] = "approved"
        checkpoints.append(normalized)

    pending = None
    if waiting_for_approval and active_checkpoint_id:
        pending = next(
            (
                item
                for item in checkpoints
                if item.get("checkpoint_id") == active_checkpoint_id
                and (
                    not active_checkpoint_lineage_id
                    or not str(item.get("lineage_id", "")).strip()
                    or str(item.get("lineage_id", "")).strip() == active_checkpoint_lineage_id
                )
            ),
            None,
        )
    if pending is None and waiting_for_approval:
        pending = next(
            (
                item
                for item in checkpoints
                if item.get("status") == "awaiting_review"
                and (
                    not active_checkpoint_lineage_id
                    or not str(item.get("lineage_id", "")).strip()
                    or str(item.get("lineage_id", "")).strip() == active_checkpoint_lineage_id
                )
            ),
            None,
        )
    if pending is not None and pending.get("status") != "awaiting_review" and waiting_for_approval:
        pending["status"] = "awaiting_review"
    payload = {
        "items": checkpoints,
        "pending": pending,
        "current_checkpoint_id": active_checkpoint_id,
        "current_checkpoint_lineage_id": active_checkpoint_lineage_id,
        "timeline_markdown": checkpoint_timeline_markdown([Checkpoint.from_dict(item) for item in checkpoints]),
    }
    payload.update(
        _snapshot_metadata(
            "cache_view",
            source_signature="|".join(
                (
                    _path_signature(context.paths.checkpoint_state_file),
                    _path_signature(context.paths.block_log_file),
                    _path_signature(context.paths.loop_state_file),
                )
            ),
            source_cursor={
                "checkpoint_state": _path_signature(context.paths.checkpoint_state_file),
                "block_log": _path_signature(context.paths.block_log_file),
                "loop_state": _path_signature(context.paths.loop_state_file),
                "checkpoint_count": len(checkpoints),
                "pending_checkpoint_id": active_checkpoint_id,
                "pending_checkpoint_lineage_id": active_checkpoint_lineage_id,
                "approval_requested": waiting_for_approval,
            },
            state_origin="disk",
        )
    )
    return payload


def pending_checkpoint_payload(context: ProjectContext) -> dict[str, Any] | None:
    raw = safe_json(context.paths.checkpoint_state_file, default={"checkpoints": []})
    raw_items = raw.get("checkpoints", []) if isinstance(raw, dict) else []
    block_entries = read_jsonl_tail(context.paths.block_log_file, 240)
    waiting_for_approval = bool(context.loop_state.pending_checkpoint_approval)
    active_checkpoint_id = str(context.loop_state.current_checkpoint_id or "").strip()
    active_checkpoint_lineage_id = str(context.loop_state.current_checkpoint_lineage_id or "").strip()
    if not waiting_for_approval:
        return None
    reconciled_items, _ = reconcile_checkpoint_items_from_blocks(
        raw_items if isinstance(raw_items, list) else [],
        block_entries,
    )
    checkpoints: list[dict[str, Any]] = []
    for item in reconciled_items:
        if isinstance(item, dict):
            normalized = deepcopy(item)
            normalized["deadline_at"] = str(normalized.get("deadline_at", "")).strip()
            is_active_checkpoint = bool(active_checkpoint_id) and str(normalized.get("checkpoint_id", "")).strip() == active_checkpoint_id
            if active_checkpoint_lineage_id:
                is_active_checkpoint = is_active_checkpoint and (
                    not str(normalized.get("lineage_id", "")).strip()
                    or str(normalized.get("lineage_id", "")).strip() == active_checkpoint_lineage_id
                )
            if is_active_checkpoint and normalized.get("status") != "awaiting_review":
                normalized["status"] = "awaiting_review"
            checkpoints.append(normalized)
    pending = None
    if active_checkpoint_id:
        pending = next(
            (
                item
                for item in checkpoints
                if str(item.get("checkpoint_id", "")).strip() == active_checkpoint_id
                and (
                    not active_checkpoint_lineage_id
                    or not str(item.get("lineage_id", "")).strip()
                    or str(item.get("lineage_id", "")).strip() == active_checkpoint_lineage_id
                )
            ),
            None,
        )
    if pending is None:
        pending = next(
            (
                item
                for item in checkpoints
                if item.get("status") == "awaiting_review"
                and (
                    not active_checkpoint_lineage_id
                    or not str(item.get("lineage_id", "")).strip()
                    or str(item.get("lineage_id", "")).strip() == active_checkpoint_lineage_id
                )
            ),
            None,
        )
    if pending is not None and pending.get("status") != "awaiting_review":
        pending["status"] = "awaiting_review"
        pending.update(
            _snapshot_metadata(
                "cache_view",
                source_signature="|".join(
                    (
                        _path_signature(context.paths.checkpoint_state_file),
                        _path_signature(context.paths.block_log_file),
                        _path_signature(context.paths.loop_state_file),
                    )
                ),
                source_cursor={
                    "checkpoint_state": _path_signature(context.paths.checkpoint_state_file),
                    "block_log": _path_signature(context.paths.block_log_file),
                    "loop_state": _path_signature(context.paths.loop_state_file),
                    "checkpoint_id": active_checkpoint_id,
                    "checkpoint_lineage_id": active_checkpoint_lineage_id,
                    "approval_requested": True,
                },
                state_origin="disk",
            )
        )
    return pending


def config_payload(context: ProjectContext) -> dict[str, Any]:
    payload = {
        "metadata_json": safe_json(context.paths.metadata_file, default={}) or {},
        "runtime_json": safe_json(context.paths.project_config_file, default={}) or {},
        "loop_state_json": safe_json(context.paths.loop_state_file, default={}) or {},
        "run_control_json": safe_json(context.paths.ui_control_file, default={}) or {},
    }
    payload.update(
        _snapshot_metadata(
            "persisted_state",
            source_signature=_persisted_state_source_signature(context),
            source_cursor={
                "metadata": _path_signature(context.paths.metadata_file),
                "runtime": _path_signature(context.paths.project_config_file),
                "loop_state": _path_signature(context.paths.loop_state_file),
                "run_control": _path_signature(context.paths.ui_control_file),
            },
            state_origin="disk",
        )
    )
    return payload


def config_payload_from_snapshot(context: ProjectContext, snapshot: DetailLogSnapshot) -> dict[str, Any]:
    payload = {
        "metadata_json": safe_json(context.paths.metadata_file, default={}) or {},
        "runtime_json": safe_json(context.paths.project_config_file, default={}) or {},
        "loop_state_json": snapshot.loop_state_json,
        "run_control_json": snapshot.run_control_json,
    }
    payload.update(
        _snapshot_metadata(
            "persisted_state",
            source_signature=_persisted_state_source_signature(context),
            source_cursor={
                "metadata": _path_signature(context.paths.metadata_file),
                "runtime": _path_signature(context.paths.project_config_file),
                "loop_state": _path_signature(context.paths.loop_state_file),
                "run_control": _path_signature(context.paths.ui_control_file),
                "snapshot_loop_state": bool(snapshot.loop_state_json),
                "snapshot_run_control": bool(snapshot.run_control_json),
            },
            state_origin="disk",
        )
    )
    return payload


def _load_detail_log_snapshot(context: ProjectContext) -> DetailLogSnapshot:
    ui_events = read_jsonl_tail(context.paths.ui_event_log_file, 40)
    blocks = read_jsonl_tail(context.paths.block_log_file, 240)
    passes = read_jsonl_tail(context.paths.pass_log_file, 30)
    test_runs = read_jsonl_tail(context.paths.logs_dir / "test_runs.jsonl", 20)
    return DetailLogSnapshot(
        ui_events=ui_events,
        blocks=blocks,
        passes=passes,
        test_runs=test_runs,
        latest_block=_latest_entry(blocks),
        latest_pass=_latest_entry(passes),
        run_control_json=safe_json(context.paths.ui_control_file, default={}) or {},
        loop_state_json=safe_json(context.paths.loop_state_file, default={}) or {},
    )


def bottom_panel_payload(
    context: ProjectContext,
    plan_state: ExecutionPlanState,
    codex_status: dict[str, Any],
    *,
    detail_level: str = "full",
    execution_log_lines: list[str] | None = None,
    latest_block: dict[str, Any] | None = None,
    latest_pass: dict[str, Any] | None = None,
    usage: dict[str, int] | None = None,
    runtime_insights: dict[str, Any] | None = None,
    run_control_json: Any = None,
    loop_state_json: Any = None,
    test_runs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    latest_block = latest_block if latest_block is not None else read_last_jsonl(context.paths.block_log_file) or {}
    latest_pass = latest_pass if latest_pass is not None else read_last_jsonl(context.paths.pass_log_file) or {}
    usage = usage if usage is not None else recent_usage(context)
    run_control_json = run_control_json if run_control_json is not None else safe_json(context.paths.ui_control_file, default={}) or {}
    loop_state_json = loop_state_json if loop_state_json is not None else safe_json(context.paths.loop_state_file, default={}) or {}
    execution_log_lines = (
        execution_log_lines
        if execution_log_lines is not None
        else (build_activity_lines(context, plan_state) if detail_level == "full" else [])
    )
    test_runs = test_runs if test_runs is not None else read_jsonl_tail(context.paths.logs_dir / "test_runs.jsonl", 12 if detail_level == "full" else 5)
    runtime_insights = runtime_insights if runtime_insights is not None else build_runtime_insights(context, plan_state, usage)
    return {
        "execution_log_lines": execution_log_lines,
        "event_json": {
            "latest_block": latest_block,
            "latest_pass": latest_pass,
            "run_control": run_control_json,
            "loop_state": loop_state_json,
        },
        "token_usage": usage,
        "runtime_insights": runtime_insights,
        "codex_status": codex_status,
        "test_runs": test_runs,
        "git_status": {
            "branch": context.metadata.branch,
            "repo_kind": context.metadata.repo_kind,
            "origin_url": context.metadata.origin_url,
            "current_status": context.metadata.current_status,
            "safe_revision": context.metadata.current_safe_revision,
            "last_commit_hash": context.loop_state.last_commit_hash,
            "current_checkpoint_id": context.loop_state.current_checkpoint_id,
            "current_checkpoint_lineage_id": context.loop_state.current_checkpoint_lineage_id,
            "pending_checkpoint_approval": context.loop_state.pending_checkpoint_approval,
        },
    }


def recent_usage(context: ProjectContext, pass_items: list[dict[str, Any]] | None = None) -> dict[str, int]:
    usage: dict[str, int] = {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_output_tokens": 0,
        "total_tokens": 0,
    }
    items = _tail_slice(pass_items, 25) if pass_items is not None else read_jsonl_tail(context.paths.pass_log_file, 25)
    for item in items:
        raw = item.get("usage", {})
        if not isinstance(raw, dict):
            continue
        for key in usage:
            value = raw.get(key, 0)
            if isinstance(value, int):
                usage[key] += value
    if usage["total_tokens"] <= 0:
        usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"] + usage["reasoning_output_tokens"]
    return usage


def build_activity_lines(
    context: ProjectContext,
    plan_state: ExecutionPlanState,
    *,
    ui_events: list[dict[str, Any]] | None = None,
    latest_pass: dict[str, Any] | None = None,
    blocks: list[dict[str, Any]] | None = None,
) -> list[str]:
    lines: list[str] = []
    event_items = ui_events if ui_events is not None else read_jsonl_tail(context.paths.ui_event_log_file, 30)
    for event in reversed(event_items):
        timestamp = str(event.get("timestamp", "")).strip()
        message = str(event.get("message", "")).strip()
        event_type = str(event.get("event_type", "")).strip()
        details = event.get("details", {})
        detail_suffix = ""
        if isinstance(details, dict):
            step_id = str(details.get("step_id", "")).strip()
            if step_id:
                detail_suffix = f" [{step_id}]"
        lines.append(f"{timestamp} | {event_type}{detail_suffix} | {message}")
    if lines:
        return lines

    if str(context.metadata.current_status).strip().lower().startswith("running:debug"):
        debug_pass = latest_pass if latest_pass is not None else read_last_jsonl(context.paths.pass_log_file)
        if isinstance(debug_pass, dict) and debug_pass:
            title = compact_text(str(debug_pass.get("selected_task", "")).strip(), max_chars=120)
            test_results = debug_pass.get("test_results", {})
            summary = ""
            if isinstance(test_results, dict):
                summary = compact_text(str(test_results.get("summary", "")).strip(), max_chars=120)
            rollback = str(debug_pass.get("rollback_status", "")).strip() or "debugger_invoked"
            lines.append(
                f"debugger | {rollback} | Debugging {title or 'current task'} | "
                f"{summary or 'Inspecting the failing verification logs and preparing a recovery fix.'}"
            )
            return lines
        lines.append(
            "debugger | running | Debugging current task | Inspecting the failing verification logs and preparing a recovery fix."
        )
        return lines

    block_items = blocks if blocks is not None else read_jsonl_tail(context.paths.block_log_file, 12)
    for block in reversed(block_items):
        block_index = block.get("block_index", "?")
        lineage_id = compact_text(str(block.get("lineage_id", "")).strip(), max_chars=24) or "n/a"
        status = block.get("status", "unknown")
        title = compact_text(str(block.get("selected_task", "")).strip(), max_chars=120)
        summary = compact_text(str(block.get("test_summary", "")).strip(), max_chars=120)
        lines.append(f"block {block_index} | {lineage_id} | {status} | {title} | {summary}")
    if lines:
        return lines

    if plan_state.steps:
        lines.append(f"Plan loaded with {len(plan_state.steps)} step(s).")
    else:
        lines.append("No plan has been generated yet.")
    return lines


def _list_item_cache_file(project: ProjectContext, *, archived: bool) -> Path:
    suffix = "HISTORY" if archived else "ACTIVE"
    return project.paths.state_dir / f"PROJECT_LIST_ITEM_CACHE_{suffix}.json"


def _list_item_memory_cache_key(project: ProjectContext, *, archived: bool) -> str:
    suffix = "history" if archived else "active"
    return f"{project.paths.project_root.resolve()}|{suffix}"


def _project_list_item_signature_from_registry_item(item: dict[str, Any]) -> str:
    project_root = Path(str(item.get("project_root", "")).strip()).expanduser()
    if not str(project_root).strip():
        return "missing-project-root"
    repo_kind = str(item.get("repo_kind", "")).strip().lower()
    repo_path_text = str(item.get("repo_path", "")).strip()
    repo_path = Path(repo_path_text).expanduser() if repo_path_text else None
    digest = hashlib.sha1()
    digest.update(str(project_root).encode("utf-8"))
    digest.update(_path_signature(project_root / "metadata.json").encode("utf-8"))
    digest.update(_path_signature(project_root / "project_config.json").encode("utf-8"))
    digest.update(_path_signature(project_root / "state" / "LOOP_STATE.json").encode("utf-8"))
    digest.update(_path_signature(project_root / "state" / "EXECUTION_PLAN.json").encode("utf-8"))
    block_log_file = (
        repo_path / LOCAL_PROJECT_LOG_DIRNAME / "blocks.jsonl"
        if repo_kind == "local" and repo_path is not None
        else project_root / "logs" / "blocks.jsonl"
    )
    digest.update(_path_signature(block_log_file).encode("utf-8"))
    digest.update(_path_signature(project_root / "reports" / "CLOSEOUT_REPORT.docx").encode("utf-8"))
    return digest.hexdigest()


def _workspace_listing_content_signature(orchestrator: Orchestrator) -> str:
    registry = orchestrator.workspace._read_registry()
    digest = hashlib.sha1()
    digest.update(f"workspace-listing-v{WORKSPACE_LISTING_CACHE_VERSION}".encode("utf-8"))
    digest.update(_path_signature(orchestrator.workspace.registry_file).encode("utf-8"))
    for repo_id, item in sorted(registry.get("projects", {}).items(), key=lambda pair: str(pair[0])):
        digest.update(str(repo_id).encode("utf-8"))
        digest.update(_project_list_item_signature_from_registry_item(item).encode("utf-8"))
    for archive_id, item in sorted(registry.get("history", {}).items(), key=lambda pair: str(pair[0])):
        digest.update(str(archive_id).encode("utf-8"))
        digest.update(_project_list_item_signature_from_registry_item(item).encode("utf-8"))
    return digest.hexdigest()


def _workspace_listing_cache_file(orchestrator: Orchestrator) -> Path:
    return orchestrator.workspace.workspace_root / "WORKSPACE_LISTING_CACHE.json"


def _project_list_item_content_signature(project: ProjectContext, *, archived: bool) -> str:
    digest = hashlib.sha1()
    digest.update(f"list-item-v{LIST_ITEM_CACHE_VERSION}:{'history' if archived else 'active'}".encode("utf-8"))
    digest.update(_path_signature(project.paths.metadata_file).encode("utf-8"))
    digest.update(_path_signature(project.paths.project_config_file).encode("utf-8"))
    digest.update(_path_signature(project.paths.loop_state_file).encode("utf-8"))
    digest.update(_path_signature(project.paths.execution_plan_file).encode("utf-8"))
    digest.update(_path_signature(project.paths.block_log_file).encode("utf-8"))
    digest.update(_path_signature(project.paths.closeout_report_docx_file).encode("utf-8"))
    return digest.hexdigest()


def _build_project_list_item_payload(
    orchestrator: Orchestrator,
    project: ProjectContext,
    *,
    archived: bool,
) -> dict[str, Any]:
    plan_state = orchestrator.load_execution_plan_state(project)
    execution_snapshot = context_execution_snapshot(project, plan_state)
    current_status = execution_snapshot.current_status
    detail = project.metadata.origin_url or f"Branch {project.metadata.branch}"
    progress_payload = project_progress_payload(plan_state)
    queue_priority = int(getattr(project.runtime, "background_queue_priority", 0) or 0)
    payload = {
        "repo_id": project.metadata.repo_id,
        "slug": project.metadata.slug,
        "display_name": project.metadata.display_name or project.metadata.slug,
        "repo_path": str(project.metadata.repo_path),
        "origin_url": project.metadata.origin_url,
        "branch": project.metadata.branch,
        "status": current_status,
        "detail": detail,
        "created_at": project.metadata.created_at,
        "last_run_at": project.metadata.last_run_at,
        "summary": project_summary(orchestrator, project, plan_state, current_status=current_status),
        "progress": progress_payload,
        "progress_caption": progress_payload["caption"],
        "stats": project_stats(plan_state),
        "current_step_label": progress_payload["currentStep"],
        "current_step_id": progress_payload["current_step_id"],
        "current_step_deadline_at": progress_payload["deadline_at"],
        "closeout_deadline_at": plan_state.closeout_deadline_at,
        "allow_background_queue": bool(getattr(project.runtime, "allow_background_queue", False)),
        "background_queue_priority": queue_priority,
        "queue_priority": queue_priority,
        "closeout_status": plan_state.closeout_status,
        "archived": bool(project.metadata.archived),
        "archive_id": project.metadata.archive_id or "",
        "archived_at": project.metadata.archived_at,
    }
    if archived:
        archived_at = project.metadata.archived_at or project.metadata.last_run_at or project.metadata.created_at
        history_detail = archived_at
        if project.metadata.repo_path:
            history_detail = f"{project.metadata.repo_path} | {archived_at}"
        payload.update(
            {
                "repo_id": project.metadata.archive_id or project.metadata.repo_id,
                "detail": history_detail,
                "archived": True,
                "archive_id": project.metadata.archive_id or "",
                "archived_at": archived_at,
            }
        )
    return payload


def _cached_project_list_item_payload(
    orchestrator: Orchestrator,
    project: ProjectContext,
    *,
    archived: bool,
    bypass_cache: bool = False,
) -> dict[str, Any]:
    content_signature = _project_list_item_content_signature(project, archived=archived)
    memory_cache_key = _list_item_memory_cache_key(project, archived=archived)
    memory_cached = _LIST_ITEM_PAYLOAD_MEMORY_CACHE.get(memory_cache_key)
    if not bypass_cache and (
        memory_cached is not None
        and memory_cached[0] == LIST_ITEM_CACHE_VERSION
        and memory_cached[1] == content_signature
    ):
        return _clone_cached_list_item_payload(memory_cached[2])
    cache_file = _list_item_cache_file(project, archived=archived)
    if not bypass_cache:
        cached = read_json(cache_file, default=None)
        if isinstance(cached, dict):
            cached_signature = str(cached.get("content_signature", "")).strip()
            cached_payload = cached.get("payload")
            if (
                int(cached.get("version", 0) or 0) == LIST_ITEM_CACHE_VERSION
                and cached_signature == content_signature
                and isinstance(cached_payload, dict)
            ):
                _LIST_ITEM_PAYLOAD_MEMORY_CACHE.set(memory_cache_key, (
                    LIST_ITEM_CACHE_VERSION,
                    content_signature,
                    deepcopy(cached_payload),
                ))
                return _clone_cached_list_item_payload(cached_payload)
    payload = _build_project_list_item_payload(orchestrator, project, archived=archived)
    _LIST_ITEM_PAYLOAD_MEMORY_CACHE.set(memory_cache_key, (
        LIST_ITEM_CACHE_VERSION,
        content_signature,
        deepcopy(payload),
    ))
    write_json(
        cache_file,
        {
            "version": LIST_ITEM_CACHE_VERSION,
            "content_signature": content_signature,
            "payload": payload,
        },
    )
    return payload


def project_list_item_payload(
    orchestrator: Orchestrator,
    project: ProjectContext,
    *,
    bypass_cache: bool = False,
) -> dict[str, Any]:
    return _cached_project_list_item_payload(orchestrator, project, archived=False, bypass_cache=bypass_cache)


def history_list_item_payload(
    orchestrator: Orchestrator,
    project: ProjectContext,
    *,
    bypass_cache: bool = False,
) -> dict[str, Any]:
    return _cached_project_list_item_payload(orchestrator, project, archived=True, bypass_cache=bypass_cache)


def _build_project_detail_base_payload(
    orchestrator: Orchestrator,
    project: ProjectContext,
    normalized_detail_level: str,
    load_run_control: Callable[[ProjectContext], dict[str, Any]],
    *,
    content_signature: str,
    execution_processes: Any = None,
) -> dict[str, Any]:
    normalized_execution_processes = _normalize_execution_processes(execution_processes)
    plan_state = orchestrator.load_execution_plan_state(project)
    control = load_run_control(project)
    log_snapshot: DetailLogSnapshot | None = None
    if normalized_detail_level == "full":
        log_snapshot = _load_detail_log_snapshot(project)
        recent_usage_payload = recent_usage(project, pass_items=log_snapshot.passes)
        runtime_insights = build_runtime_insights(
            project,
            plan_state,
            recent_usage_payload,
            recent_passes=log_snapshot.passes,
        )
        recent_blocks = _tail_slice(log_snapshot.blocks, 8)
        recent_passes = _tail_slice(log_snapshot.passes, 12)
        reports = report_payload(project)
        history = history_payload_from_snapshot(project, log_snapshot)
        checkpoint_state = safe_json(project.paths.checkpoint_state_file, default={"checkpoints": []})
        checkpoint_items = checkpoint_state.get("checkpoints", []) if isinstance(checkpoint_state, dict) else []
        checkpoints = checkpoint_payload_from_blocks(
            project,
            checkpoint_items if isinstance(checkpoint_items, list) else [],
            log_snapshot.blocks,
        )
        config = config_payload_from_snapshot(project, log_snapshot)
        chat = chat_payload(project, message_limit=120)
        workspace_tree = managed_workspace_tree(project)
        activity = build_activity_lines(
            project,
            plan_state,
            ui_events=_tail_slice(log_snapshot.ui_events, 30),
            latest_pass=log_snapshot.latest_pass,
            blocks=_tail_slice(log_snapshot.blocks, 12),
        )
        planning_progress = build_planning_progress(_tail_slice(log_snapshot.ui_events, 30))
        latest_block = log_snapshot.latest_block
        latest_pass = log_snapshot.latest_pass
    else:
        ui_events = read_jsonl_tail(project.paths.ui_event_log_file, 20)
        recent_pass_items = read_jsonl_tail(project.paths.pass_log_file, 25)
        recent_usage_payload = recent_usage(project, pass_items=recent_pass_items)
        runtime_insights = build_runtime_insights(
            project,
            plan_state,
            recent_usage_payload,
            recent_passes=recent_pass_items,
        )
        recent_blocks = []
        recent_passes = []
        pending_checkpoint = pending_checkpoint_payload(project)
        reports = {"latest_failure": latest_failure_payload(project)}
        history = {
            "ui_events": [],
            "blocks": [],
            "passes": [],
            "test_runs": [],
            **_flow_svg_payload(project),
        }
        checkpoints = {
            "items": [],
            "pending": pending_checkpoint,
            "timeline_markdown": "",
        }
        config = {}
        chat = chat_payload(
            project,
            message_limit=0,
            include_messages=False,
            include_summary=False,
        )
        workspace_tree = []
        activity = build_activity_lines(project, plan_state, ui_events=ui_events)[:8]
        planning_progress = build_planning_progress(ui_events)
        latest_block = {}
        latest_pass = {}
    execution_snapshot = context_execution_snapshot(
        project,
        plan_state,
        planning_progress=planning_progress,
    )
    current_status = execution_snapshot.current_status
    progress_payload = project_progress_payload(plan_state)
    loop_state_payload = project.loop_state.to_dict()
    execution_state = build_execution_state_payload(
        current_status,
        display_status=execution_snapshot.display_status,
        planning_running=execution_snapshot.planning_running,
        loop_state=loop_state_payload,
        checkpoints=checkpoints,
        execution_processes=normalized_execution_processes,
    )
    bottom_panels = bottom_panel_payload(
        project,
        plan_state,
        {},
        detail_level=normalized_detail_level,
        execution_log_lines=activity if normalized_detail_level == "full" else None,
        latest_block=latest_block,
        latest_pass=latest_pass,
        usage=recent_usage_payload,
        runtime_insights=runtime_insights,
        run_control_json=log_snapshot.run_control_json if normalized_detail_level == "full" else None,
        loop_state_json=log_snapshot.loop_state_json if normalized_detail_level == "full" else None,
        test_runs=_tail_slice(log_snapshot.test_runs, 12) if normalized_detail_level == "full" else None,
    )
    if isinstance(bottom_panels.get("git_status"), dict):
        bottom_panels["git_status"]["current_status"] = current_status
    generated_at = now_utc_iso()
    snapshot_sources = _project_detail_snapshot_sources(
        project,
        normalized_detail_level=normalized_detail_level,
        content_signature=content_signature,
        codex_status={},
        generated_at=generated_at,
    )
    project_payload = project.metadata.to_dict()
    project_payload["current_status"] = current_status
    snapshot = {
        "project": deepcopy(project_payload),
        "loop_state": deepcopy(loop_state_payload),
        "snapshot_kind": "cache_view",
        "snapshot_epoch": _snapshot_epoch_ms(),
        "snapshot_id": _snapshot_metadata(
            "cache_view",
            source_signature=content_signature,
            source_cursor={
                "detail_level": normalized_detail_level,
                "project_root": str(project.paths.project_root),
                "repo_id": project.metadata.repo_id,
            },
            state_origin="cache_view",
            generated_at=generated_at,
            content_signature=content_signature,
        )["snapshot_id"],
        "generated_at": generated_at,
        "state_origin": "cache_view",
        "source_signature": content_signature,
        "source_cursor": {
            "detail_level": normalized_detail_level,
            "project_root": str(project.paths.project_root),
            "repo_id": project.metadata.repo_id,
        },
        "snapshot_sources": snapshot_sources,
    }
    return {
        "detail_level": normalized_detail_level,
        "project": project_payload,
        "runtime": project.runtime.to_dict(),
        "loop_state": loop_state_payload,
        "plan": plan_state.to_dict(),
        "execution_processes": normalized_execution_processes,
        "execution_state": execution_state,
        "summary": project_summary(
            orchestrator,
            project,
            plan_state,
            current_status=current_status,
            recent_blocks=_tail_slice(log_snapshot.blocks, 5) if normalized_detail_level == "full" else None,
        ),
        "progress": progress_payload,
        "progress_caption": progress_payload["caption"],
        "stats": project_stats(plan_state),
        "current_step_label": progress_payload["currentStep"],
        "current_step_id": progress_payload["current_step_id"],
        "current_step_deadline_at": progress_payload["deadline_at"],
        "closeout_deadline_at": plan_state.closeout_deadline_at,
        "queue_priority": int(getattr(project.runtime, "background_queue_priority", 0) or 0),
        "codex_status": {},
        "activity": activity,
        "planning_progress": planning_progress,
        "runtime_insights": runtime_insights,
        "snapshot": snapshot,
        "run_control": control,
        "recent_blocks": recent_blocks,
        "recent_passes": recent_passes,
        "workspace_tree": workspace_tree,
        "reports": reports,
        "history": history,
        "checkpoints": checkpoints,
        "config": config,
        "chat": chat,
        "snapshot_sources": snapshot_sources,
        "files": {
            "project_root": str(project.paths.project_root),
            "repo_dir": str(project.paths.repo_dir),
            "execution_plan_file": str(project.paths.execution_plan_file),
            "ui_control_file": str(project.paths.ui_control_file),
            "ui_event_log_file": str(project.paths.ui_event_log_file),
            "chat_sessions_file": str(chat_sessions_registry_file(project)),
            "chat_active_session_file": str(chat_active_session_file(project)),
            "closeout_report_file": str(project.paths.closeout_report_file),
            "word_report_file": str(project.paths.closeout_report_docx_file),
            "powerpoint_report_file": str(project.paths.closeout_report_pptx_file),
            "ml_experiment_report_file": str(project.paths.ml_experiment_report_file),
            "spine_file": str(project.paths.spine_file),
            "common_requirements_file": str(project.paths.common_requirements_file),
            "contract_wave_audit_file": str(project.paths.contract_wave_audit_file),
            "shared_contracts_file": str(project.paths.shared_contracts_file),
            "lineage_manifests_dir": str(project.paths.lineage_manifests_dir),
        },
        "bottom_panels": bottom_panels,
        "github": {
            "connected": bool(project.metadata.origin_url),
            "origin_url": project.metadata.origin_url,
            "repo_url": project.metadata.repo_url,
            "branch": project.metadata.branch,
        },
        "share": (
            project_share_payload(orchestrator.workspace.workspace_root, project)
            if normalized_detail_level == "full"
            else project_share_config_payload(orchestrator.workspace.workspace_root, project)
        ),
    }


def _cached_project_detail_base_payload(
    orchestrator: Orchestrator,
    project: ProjectContext,
    normalized_detail_level: str,
    load_run_control: Callable[[ProjectContext], dict[str, Any]],
    *,
    execution_processes: Any = None,
    bypass_cache: bool = False,
) -> tuple[dict[str, Any], str, bool, dict[str, Any]]:
    timings: dict[str, Any] = {
        "detail_level": normalized_detail_level,
    }
    started_at = perf_counter()
    content_signature = project_detail_content_signature(
        project,
        normalized_detail_level,
        execution_processes=execution_processes,
    )
    timings["content_signature_ms"] = round((perf_counter() - started_at) * 1000.0, 3)
    cache_file = _detail_cache_file(project, normalized_detail_level)
    memory_cache_key = f"{project.paths.project_root.resolve()}|{normalized_detail_level}"
    memory_cached = _DETAIL_BASE_PAYLOAD_MEMORY_CACHE.get(memory_cache_key)
    if not bypass_cache and (
        cache_file.exists()
        and
        memory_cached is not None
        and memory_cached[0] == DETAIL_CACHE_VERSION
        and memory_cached[1] == content_signature
    ):
        timings["cache_lookup_ms"] = 0.0
        timings["cache_hit"] = True
        timings["base_build_ms"] = 0.0
        timings["cache_write_ms"] = 0.0
        return _clone_cached_detail_payload(memory_cached[2]), content_signature, True, timings
    cache_lookup_started_at = perf_counter()
    cached = read_json(cache_file, default=None)
    if not bypass_cache and isinstance(cached, dict):
        cached_signature = str(cached.get("content_signature", "")).strip()
        cached_payload = cached.get("payload")
        if (
            int(cached.get("version", 0) or 0) == DETAIL_CACHE_VERSION
            and cached_signature == content_signature
            and isinstance(cached_payload, dict)
        ):
            _DETAIL_BASE_PAYLOAD_MEMORY_CACHE.set(memory_cache_key, (
                DETAIL_CACHE_VERSION,
                content_signature,
                deepcopy(cached_payload),
            ))
            payload = cached_payload
            payload["content_signature"] = content_signature
            payload["payload_cache_hit"] = True
            timings["cache_lookup_ms"] = round((perf_counter() - cache_lookup_started_at) * 1000.0, 3)
            timings["cache_hit"] = True
            timings["base_build_ms"] = 0.0
            timings["cache_write_ms"] = 0.0
            return _clone_cached_detail_payload(payload), content_signature, True, timings
    timings["cache_lookup_ms"] = round((perf_counter() - cache_lookup_started_at) * 1000.0, 3)
    base_build_started_at = perf_counter()
    payload = _build_project_detail_base_payload(
        orchestrator,
        project,
        normalized_detail_level,
        load_run_control,
        content_signature=content_signature,
        execution_processes=execution_processes,
    )
    timings["base_build_ms"] = round((perf_counter() - base_build_started_at) * 1000.0, 3)
    payload["content_signature"] = content_signature
    payload["payload_cache_hit"] = False
    _DETAIL_BASE_PAYLOAD_MEMORY_CACHE.set(memory_cache_key, (
        DETAIL_CACHE_VERSION,
        content_signature,
        deepcopy(payload),
    ))
    cache_write_started_at = perf_counter()
    write_json(
        cache_file,
        {
            "version": DETAIL_CACHE_VERSION,
            "content_signature": content_signature,
            "payload": payload,
        },
    )
    timings["cache_write_ms"] = round((perf_counter() - cache_write_started_at) * 1000.0, 3)
    timings["cache_hit"] = False
    return payload, content_signature, False, timings


def _finalize_project_detail_payload(
    base_payload: dict[str, Any],
    *,
    content_signature: str,
    codex_status: dict[str, Any],
    payload_cache_hit: bool,
) -> dict[str, Any]:
    payload = base_payload
    payload["codex_status"] = codex_status
    payload["content_signature"] = content_signature
    payload["detail_signature"] = _detail_signature(content_signature, codex_status)
    payload["payload_cache_hit"] = payload_cache_hit
    snapshot_sources = payload.get("snapshot_sources")
    if not isinstance(snapshot_sources, dict):
        snapshot_sources = {}
    snapshot_sources = deepcopy(snapshot_sources)
    snapshot_sources["live_runtime"] = _snapshot_metadata(
        "live_runtime",
        source_signature=hashlib.sha1(json.dumps(codex_status, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
        source_cursor={
            "codex_status_keys": sorted(codex_status.keys()) if isinstance(codex_status, dict) else [],
            "provider_statuses_keys": sorted((codex_status.get("provider_statuses") or {}).keys())
            if isinstance(codex_status, dict) and isinstance(codex_status.get("provider_statuses"), dict)
            else [],
        },
        state_origin="process",
        generated_at=payload.get("generated_at") if isinstance(payload.get("generated_at"), str) else None,
        content_signature=content_signature,
        detail_signature=payload["detail_signature"],
    )
    payload["snapshot_sources"] = snapshot_sources
    snapshot = payload.get("snapshot")
    if isinstance(snapshot, dict):
        snapshot["snapshot_kind"] = "cache_view"
        snapshot["snapshot_id"] = _snapshot_metadata(
            "cache_view",
            source_signature=content_signature,
            source_cursor=snapshot.get("source_cursor", {}),
            state_origin="cache_view",
            generated_at=snapshot.get("generated_at") if isinstance(snapshot.get("generated_at"), str) else None,
            content_signature=content_signature,
            detail_signature=payload["detail_signature"],
        )["snapshot_id"]
        snapshot["detail_signature"] = payload["detail_signature"]
    bottom_panels = payload.get("bottom_panels")
    if isinstance(bottom_panels, dict):
        bottom_panels["codex_status"] = codex_status
    return payload


def _provider_statuses_for_detail(
    *,
    fetch_codex_status: Callable[[str], Any],
    refresh_codex_status: bool,
) -> dict[str, dict[str, Any]]:
    global _PROVIDER_STATUSES_FETCH_CACHE
    if not refresh_codex_status:
        return provider_statuses_payload()
    if _PROVIDER_STATUSES_FETCH_CACHE is not None:
        checked_at, cached_statuses = _PROVIDER_STATUSES_FETCH_CACHE
        if (monotonic() - checked_at) <= _PROVIDER_STATUSES_FETCH_CACHE_TTL_SECONDS:
            return deepcopy(cached_statuses)
    statuses = provider_statuses_payload(
        fetch_snapshot=fetch_codex_status,
    )
    _PROVIDER_STATUSES_FETCH_CACHE = (monotonic(), deepcopy(statuses))
    return statuses


def project_detail_payload(
    orchestrator: Orchestrator,
    project: ProjectContext,
    *,
    load_run_control: Callable[[ProjectContext], dict[str, Any]],
    fetch_codex_status: Callable[[str], Any] = fetch_codex_backend_snapshot,
    refresh_codex_status: bool = True,
    detail_level: str = "full",
    execution_processes: Any = None,
    bypass_detail_cache: bool = False,
) -> dict[str, Any]:
    normalized_detail_level = "core" if str(detail_level).strip().lower() == "core" else "full"
    detail_started_at = perf_counter()
    base_payload, content_signature, payload_cache_hit, perf_details = _cached_project_detail_base_payload(
        orchestrator,
        project,
        normalized_detail_level,
        load_run_control,
        execution_processes=execution_processes,
        bypass_cache=bypass_detail_cache,
    )
    codex_started_at = perf_counter()
    codex_status = (
        fetch_codex_status(project.runtime.codex_path).to_dict()
        if refresh_codex_status
        else {}
    )
    perf_details["codex_status_ms"] = round((perf_counter() - codex_started_at) * 1000.0, 3)
    if isinstance(codex_status, dict):
        provider_statuses_started_at = perf_counter()
        codex_status["provider_statuses"] = _provider_statuses_for_detail(
            fetch_codex_status=fetch_codex_status,
            refresh_codex_status=refresh_codex_status,
        )
        perf_details["provider_statuses_ms"] = round((perf_counter() - provider_statuses_started_at) * 1000.0, 3)
    finalize_started_at = perf_counter()
    payload = _finalize_project_detail_payload(
        base_payload,
        content_signature=content_signature,
        codex_status=codex_status,
        payload_cache_hit=payload_cache_hit,
    )
    perf_details["finalize_ms"] = round((perf_counter() - finalize_started_at) * 1000.0, 3)
    perf_details["total_ms"] = round((perf_counter() - detail_started_at) * 1000.0, 3)
    perf_details["refresh_codex_status"] = bool(refresh_codex_status)
    perf_details["payload_cache_hit"] = bool(payload_cache_hit)
    _detail_perf_log(project, "project-detail-built", perf_details)
    return payload


def list_projects_payload(orchestrator: Orchestrator, *, bypass_cache: bool = False) -> dict[str, Any]:
    memory_cache_key = str(orchestrator.workspace.workspace_root.resolve())
    content_signature = _workspace_listing_content_signature(orchestrator)
    memory_cached = _WORKSPACE_LISTING_MEMORY_CACHE.get(memory_cache_key)
    if not bypass_cache and (
        memory_cached is not None
        and memory_cached[0] == WORKSPACE_LISTING_CACHE_VERSION
        and memory_cached[1] == content_signature
    ):
        return _clone_workspace_listing_payload(memory_cached[2])
    cache_file = _workspace_listing_cache_file(orchestrator)
    if not bypass_cache:
        cached = read_json(cache_file, default=None)
        if isinstance(cached, dict):
            cached_signature = str(cached.get("content_signature", "")).strip()
            cached_payload = cached.get("payload")
            if (
                int(cached.get("version", 0) or 0) == WORKSPACE_LISTING_CACHE_VERSION
                and cached_signature == content_signature
                and isinstance(cached_payload, dict)
            ):
                _WORKSPACE_LISTING_MEMORY_CACHE.set(memory_cache_key, (
                    WORKSPACE_LISTING_CACHE_VERSION,
                    content_signature,
                    deepcopy(cached_payload),
                ))
                return _clone_workspace_listing_payload(cached_payload)
    projects = sorted(orchestrator.list_projects(), key=lambda item: item.metadata.created_at, reverse=True)
    project_payloads = [project_list_item_payload(orchestrator, project, bypass_cache=bypass_cache) for project in projects]
    history_projects = orchestrator.workspace.list_history_projects()
    history_payloads = [history_list_item_payload(orchestrator, project, bypass_cache=bypass_cache) for project in history_projects]
    payload = {
        "projects": project_payloads,
        "history": history_payloads,
        "workspace": workspace_snapshot([str(item.get("status", "")).strip() for item in project_payloads]),
    }
    _WORKSPACE_LISTING_MEMORY_CACHE.set(memory_cache_key, (
        WORKSPACE_LISTING_CACHE_VERSION,
        content_signature,
        deepcopy(payload),
    ))
    write_json(
        cache_file,
        {
            "version": WORKSPACE_LISTING_CACHE_VERSION,
            "content_signature": content_signature,
            "payload": payload,
        },
    )
    return payload
