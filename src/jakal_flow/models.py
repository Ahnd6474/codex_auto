from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any
import re

from .platform_defaults import default_codex_path


def _normalize(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return {key: _normalize(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        items = re.split(r"[\r\n,]+", value)
    else:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item).strip()
        if not text:
            continue
        if text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_default(value: Any, default: int, minimum: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None:
        return max(minimum, parsed)
    return parsed


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_execution_step_model(model_provider: Any, model: Any) -> str:
    normalized_provider = str(model_provider or "").strip().lower()
    normalized_model = str(model or "").strip().lower()
    if normalized_model == "codex" and normalized_provider in {"openai", "ensemble"}:
        return ""
    return normalized_model


@dataclass(slots=True)
class RuntimeOptions:
    repo_backend: str = "auto"
    model_provider: str = "openai"
    local_model_provider: str = ""
    chat_model_provider: str = ""
    chat_local_model_provider: str = ""
    provider_base_url: str = ""
    provider_api_key_env: str = ""
    ensemble_openai_model: str = "gpt-5.4"
    ensemble_gemini_model: str = "gemini-3-flash-preview"
    ensemble_claude_model: str = "claude-sonnet-4-6"
    billing_mode: str = "included"
    input_cost_per_million_usd: float = 0.0
    cached_input_cost_per_million_usd: float = 0.0
    output_cost_per_million_usd: float = 0.0
    reasoning_output_cost_per_million_usd: float = 0.0
    per_pass_cost_usd: float = 0.0
    model: str = "auto"
    execution_model: str = ""
    model_preset: str = "auto"
    model_selection_mode: str = "slug"
    model_slug_input: str = ""
    chat_model: str = ""
    effort_selection_mode: str = "explicit"
    planning_mode: str = "full"
    use_fast_mode: bool = False
    generate_word_report: bool = False
    codex_base_slug: str = ""
    codex_variant_slug: str = ""
    effort: str = "medium"
    planning_effort: str = ""
    workflow_mode: str = "standard"
    ml_max_cycles: int = 3
    execution_mode: str = "parallel"
    allow_background_queue: bool = True
    background_queue_priority: int = 0
    parallel_worker_mode: str = "auto"
    parallel_workers: int = 0
    parallel_memory_per_worker_gib: float = 3.0
    save_project_logs: bool = False
    extra_prompt: str = ""
    init_plan_prompt: str = ""
    approval_mode: str = "never"
    sandbox_mode: str = "workspace-write"
    test_cmd: str = "python -m pytest"
    verification_profiles: dict[str, str] = field(default_factory=dict)
    max_blocks: int = 1
    allow_push: bool = False
    auto_merge_pull_request: bool = False
    codex_path: str = field(default_factory=default_codex_path)
    git_user_name: str = "jakal-flow-bot"
    git_user_email: str = "jakal-flow@example.invalid"
    no_progress_limit: int = 3
    regression_limit: int = 3
    empty_cycle_limit: int = 3
    checkpoint_interval_blocks: int = 2
    require_checkpoint_approval: bool = True
    optimization_mode: str = "off"
    optimization_large_file_lines: int = 350
    optimization_long_function_lines: int = 80
    optimization_duplicate_block_lines: int = 4
    optimization_max_files: int = 3

    def __post_init__(self) -> None:
        normalized_provider = str(self.model_provider or "").strip().lower()
        current_path = str(self.codex_path or "").strip()
        legacy_default_path = default_codex_path()
        provider_default_path = default_codex_path(normalized_provider)
        if not current_path or (provider_default_path != legacy_default_path and current_path == legacy_default_path):
            self.codex_path = provider_default_path

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "RuntimeOptions":
        if not isinstance(data, dict):
            return cls()
        allowed = {item.name for item in fields(cls)}
        normalized = {key: value for key, value in data.items() if key in allowed}
        return cls(**normalized)

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)


@dataclass(slots=True)
class RepoMetadata:
    repo_id: str
    slug: str
    repo_url: str
    branch: str
    project_root: Path
    repo_path: Path
    created_at: str
    last_run_at: str | None = None
    current_status: str = "initialized"
    current_safe_revision: str | None = None
    repo_kind: str = "remote"
    vcs_backend: str = "git"
    display_name: str | None = None
    origin_url: str | None = None
    local_logs_mode: str = "repo"
    archived: bool = False
    archive_id: str | None = None
    archived_at: str | None = None
    source_repo_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "RepoMetadata":
        payload = data if isinstance(data, dict) else {}
        return cls(
            repo_id=str(payload.get("repo_id", "")).strip(),
            slug=str(payload.get("slug", "")).strip(),
            repo_url=str(payload.get("repo_url", "")).strip(),
            branch=str(payload.get("branch", "")).strip(),
            project_root=Path(str(payload.get("project_root", "")).strip()),
            repo_path=Path(str(payload.get("repo_path", "")).strip()),
            created_at=str(payload.get("created_at", "")).strip(),
            last_run_at=_optional_str(payload.get("last_run_at")),
            current_status=str(payload.get("current_status", "initialized")).strip() or "initialized",
            current_safe_revision=_optional_str(payload.get("current_safe_revision")),
            repo_kind=str(payload.get("repo_kind", "remote")).strip() or "remote",
            vcs_backend=str(payload.get("vcs_backend", "git")).strip() or "git",
            display_name=_optional_str(payload.get("display_name")),
            origin_url=_optional_str(payload.get("origin_url")),
            local_logs_mode=str(payload.get("local_logs_mode", "repo")).strip() or "repo",
            archived=bool(payload.get("archived", False)),
            archive_id=_optional_str(payload.get("archive_id")),
            archived_at=_optional_str(payload.get("archived_at")),
            source_repo_id=_optional_str(payload.get("source_repo_id")),
        )

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)


@dataclass(slots=True)
class LoopCounters:
    no_progress_blocks: int = 0
    regression_failures: int = 0
    empty_cycles: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "LoopCounters":
        payload = data if isinstance(data, dict) else {}
        return cls(
            no_progress_blocks=_int_or_default(payload.get("no_progress_blocks", 0), 0, minimum=0),
            regression_failures=_int_or_default(payload.get("regression_failures", 0), 0, minimum=0),
            empty_cycles=_int_or_default(payload.get("empty_cycles", 0), 0, minimum=0),
        )


@dataclass(slots=True)
class LoopState:
    repo_id: str
    repo_slug: str
    block_index: int = 0
    last_block_completed_at: str | None = None
    current_task: str | None = None
    last_candidates: list[dict[str, Any]] = field(default_factory=list)
    last_commit_hash: str | None = None
    current_safe_revision: str | None = None
    plan_locked: bool = True
    stop_reason: str | None = None
    stop_requested: bool = False
    current_checkpoint_id: str | None = None
    current_checkpoint_lineage_id: str | None = None
    pending_checkpoint_approval: bool = False
    counters: LoopCounters = field(default_factory=LoopCounters)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "LoopState":
        payload = data if isinstance(data, dict) else {}
        return cls(
            repo_id=str(payload.get("repo_id", "")).strip(),
            repo_slug=str(payload.get("repo_slug", "")).strip(),
            block_index=_int_or_default(payload.get("block_index", 0), 0, minimum=0),
            last_block_completed_at=_optional_str(payload.get("last_block_completed_at")),
            current_task=_optional_str(payload.get("current_task")),
            last_candidates=payload.get("last_candidates", []) if isinstance(payload.get("last_candidates", []), list) else [],
            last_commit_hash=_optional_str(payload.get("last_commit_hash")),
            current_safe_revision=_optional_str(payload.get("current_safe_revision")),
            plan_locked=bool(payload.get("plan_locked", True)),
            stop_reason=_optional_str(payload.get("stop_reason")),
            stop_requested=bool(payload.get("stop_requested", False)),
            current_checkpoint_id=_optional_str(payload.get("current_checkpoint_id")),
            current_checkpoint_lineage_id=_optional_str(payload.get("current_checkpoint_lineage_id")),
            pending_checkpoint_approval=bool(payload.get("pending_checkpoint_approval", False)),
            counters=LoopCounters.from_dict(payload.get("counters")),
        )

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)


@dataclass(slots=True)
class ProjectPaths:
    workspace_root: Path
    projects_root: Path
    project_root: Path
    repo_dir: Path
    docs_dir: Path
    memory_dir: Path
    logs_dir: Path
    reports_dir: Path
    state_dir: Path
    review_dir: Path
    metadata_file: Path
    project_config_file: Path
    loop_state_file: Path
    plan_file: Path
    mid_term_plan_file: Path
    scope_guard_file: Path
    active_task_file: Path
    block_review_file: Path
    checkpoint_timeline_file: Path
    research_notes_file: Path
    attempt_history_file: Path
    success_patterns_file: Path
    failure_patterns_file: Path
    task_summaries_file: Path
    pass_log_file: Path
    block_log_file: Path
    planning_metrics_file: Path
    checkpoint_state_file: Path
    execution_plan_file: Path
    planning_inputs_cache_file: Path
    planning_prompt_cache_file: Path
    block_plan_cache_file: Path
    lineage_state_file: Path
    spine_file: Path
    common_requirements_file: Path
    contract_wave_audit_file: Path
    ml_mode_state_file: Path
    ml_step_report_file: Path
    ml_experiment_reports_dir: Path
    lineage_manifests_dir: Path
    ui_control_file: Path
    ui_event_log_file: Path
    execution_flow_svg_file: Path
    closeout_report_file: Path
    closeout_report_docx_file: Path
    closeout_report_pptx_file: Path
    requirements_matrix_file: Path
    global_test_plan_file: Path
    test_strength_report_file: Path
    reviewer_a_verdict_file: Path
    reviewer_b_decision_file: Path
    replan_packet_file: Path
    ml_experiment_report_file: Path
    ml_experiment_results_svg_file: Path
    shared_contracts_file: Path

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ProjectPaths":
        payload = data if isinstance(data, dict) else {}
        return cls(**{item.name: Path(str(payload.get(item.name, "")).strip()) for item in fields(cls)})

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)


@dataclass(slots=True)
class ProjectContext:
    metadata: RepoMetadata
    runtime: RuntimeOptions
    paths: ProjectPaths
    loop_state: LoopState

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ProjectContext":
        payload = data if isinstance(data, dict) else {}
        return cls(
            metadata=RepoMetadata.from_dict(payload.get("metadata")),
            runtime=RuntimeOptions.from_dict(payload.get("runtime")),
            paths=ProjectPaths.from_dict(payload.get("paths")),
            loop_state=LoopState.from_dict(payload.get("loop_state")),
        )

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)


@dataclass(slots=True)
class LineageState:
    lineage_id: str
    branch_name: str
    worktree_dir: Path
    project_root: Path
    created_at: str
    updated_at: str
    head_commit: str = ""
    safe_revision: str = ""
    status: str = "active"
    parent_lineage_id: str | None = None
    source_step_id: str | None = None
    last_step_id: str | None = None
    merged_by_step_id: str | None = None
    step_ids: list[str] = field(default_factory=list)
    notes: str = ""
    manifest_files: list[str] = field(default_factory=list)
    latest_promotion_class: str = ""
    latest_spine_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LineageState":
        return cls(
            lineage_id=str(data.get("lineage_id", "")).strip(),
            branch_name=str(data.get("branch_name", "")).strip(),
            worktree_dir=Path(str(data.get("worktree_dir", "")).strip()),
            project_root=Path(str(data.get("project_root", "")).strip()),
            created_at=str(data.get("created_at", "")).strip(),
            updated_at=str(data.get("updated_at", "")).strip(),
            head_commit=str(data.get("head_commit", "")).strip(),
            safe_revision=str(data.get("safe_revision", "")).strip(),
            status=str(data.get("status", "active")).strip() or "active",
            parent_lineage_id=_optional_str(data.get("parent_lineage_id")),
            source_step_id=_optional_str(data.get("source_step_id")),
            last_step_id=_optional_str(data.get("last_step_id")),
            merged_by_step_id=_optional_str(data.get("merged_by_step_id")),
            step_ids=_string_list(data.get("step_ids", [])),
            notes=str(data.get("notes", "")).strip(),
            manifest_files=_string_list(data.get("manifest_files", [])),
            latest_promotion_class=str(data.get("latest_promotion_class", "")).strip().lower(),
            latest_spine_version=str(data.get("latest_spine_version", "")).strip(),
        )


@dataclass(slots=True)
class CandidateTask:
    candidate_id: str
    title: str
    rationale: str
    plan_refs: list[str]
    score: float

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)


@dataclass(slots=True)
class MemoryEntry:
    timestamp: str
    task: str
    summary: str
    tags: list[str]
    block_index: int
    commit_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)


@dataclass(slots=True)
class CodexRunResult:
    pass_type: str
    prompt_file: Path
    output_file: Path
    event_file: Path
    returncode: int
    search_enabled: bool
    changed_files: list[str]
    usage: dict[str, int] = field(default_factory=dict)
    last_message: str | None = None
    attempt_count: int = 1
    duration_seconds: float = 0.0
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)


@dataclass(slots=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


@dataclass(slots=True)
class TestRunResult:
    command: str
    returncode: int
    stdout_file: Path
    stderr_file: Path
    summary: str
    failure_reason: str = ""
    duration_seconds: float = 0.0
    source_duration_seconds: float = 0.0
    cache_hit: bool = False
    state_fingerprint: str | None = None
    cache_key: str | None = None
    verification_profile: str = ""
    verification_profile_source: str = ""
    verification_profile_reason: str = ""
    verification_command_source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)


@dataclass(slots=True)
class Checkpoint:
    checkpoint_id: str
    title: str
    plan_refs: list[str]
    target_block: int
    deadline_at: str = ""
    status: str = "pending"
    created_at: str | None = None
    reached_at: str | None = None
    lineage_id: str = ""
    approved_at: str | None = None
    review_notes: str = ""
    commit_hashes: list[str] = field(default_factory=list)
    pushed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Checkpoint":
        return cls(
            checkpoint_id=str(data.get("checkpoint_id", "")).strip(),
            title=str(data.get("title", "")).strip(),
            plan_refs=_string_list(data.get("plan_refs", [])),
            target_block=_int_or_default(data.get("target_block", 0), 0, minimum=0),
            deadline_at=str(data.get("deadline_at", "")).strip(),
            status=str(data.get("status", "pending")).strip() or "pending",
            created_at=_optional_str(data.get("created_at")),
            reached_at=_optional_str(data.get("reached_at")),
            lineage_id=str(data.get("lineage_id", "")).strip(),
            approved_at=_optional_str(data.get("approved_at")),
            review_notes=str(data.get("review_notes", "")).strip(),
            commit_hashes=_string_list(data.get("commit_hashes", [])),
            pushed=bool(data.get("pushed", False)),
        )


@dataclass(slots=True)
class ExecutionStep:
    step_id: str
    title: str
    display_description: str = ""
    codex_description: str = ""
    deadline_at: str = ""
    model_provider: str = ""
    model: str = ""
    test_command: str = ""
    success_criteria: str = ""
    step_type: str = ""
    scope_class: str = ""
    spine_version: str = ""
    shared_contracts: list[str] = field(default_factory=list)
    verification_profile: str = ""
    promotion_class: str = ""
    primary_scope_paths: list[str] = field(default_factory=list)
    shared_reviewed_paths: list[str] = field(default_factory=list)
    forbidden_core_paths: list[str] = field(default_factory=list)
    reasoning_effort: str = ""
    parallel_group: str = ""
    depends_on: list[str] = field(default_factory=list)
    owned_paths: list[str] = field(default_factory=list)
    status: str = "pending"
    started_at: str | None = None
    completed_at: str | None = None
    commit_hash: str | None = None
    notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionStep":
        legacy_description = str(data.get("description", "")).strip()
        display_description = str(data.get("display_description", "")).strip() or legacy_description
        codex_description = str(data.get("codex_description", "")).strip() or legacy_description or display_description
        metadata = data.get("metadata", {}) if isinstance(data.get("metadata", {}), dict) else {}
        return cls(
            step_id=str(data.get("step_id", "")).strip() or "ST1",
            title=str(data.get("title", data.get("task_title", ""))).strip(),
            display_description=display_description,
            codex_description=codex_description,
            deadline_at=str(data.get("deadline_at", "")).strip(),
            model_provider=str(data.get("model_provider", "")).strip().lower(),
            model=_normalize_execution_step_model(
                data.get("model_provider", ""),
                data.get("model", data.get("model_slug_input", "")),
            ),
            test_command=str(data.get("test_command", "")).strip(),
            success_criteria=str(data.get("success_criteria", "")).strip(),
            step_type=str(data.get("step_type", metadata.get("step_type", ""))).strip().lower(),
            scope_class=str(data.get("scope_class", metadata.get("scope_class", ""))).strip().lower(),
            spine_version=str(data.get("spine_version", metadata.get("spine_version", ""))).strip(),
            shared_contracts=_string_list(data.get("shared_contracts", metadata.get("shared_contracts", []))),
            verification_profile=str(data.get("verification_profile", metadata.get("verification_profile", ""))).strip().lower(),
            promotion_class=str(data.get("promotion_class", metadata.get("promotion_class", ""))).strip().lower(),
            primary_scope_paths=_string_list(data.get("primary_scope_paths", metadata.get("primary_scope_paths", []))),
            shared_reviewed_paths=_string_list(data.get("shared_reviewed_paths", metadata.get("shared_reviewed_paths", []))),
            forbidden_core_paths=_string_list(data.get("forbidden_core_paths", metadata.get("forbidden_core_paths", []))),
            reasoning_effort=str(data.get("reasoning_effort", data.get("effort", ""))).strip().lower(),
            parallel_group=str(data.get("parallel_group", "")).strip(),
            depends_on=_string_list(data.get("depends_on", [])),
            owned_paths=_string_list(data.get("owned_paths", metadata.get("owned_paths", []))),
            status=str(data.get("status", "pending")).strip() or "pending",
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            commit_hash=data.get("commit_hash"),
            notes=str(data.get("notes", "")).strip(),
            metadata=metadata,
        )


@dataclass(slots=True)
class ExecutionPlanState:
    plan_title: str = ""
    project_prompt: str = ""
    summary: str = ""
    workflow_mode: str = "standard"
    execution_mode: str = "parallel"
    default_test_command: str = "python -m pytest"
    last_updated_at: str | None = None
    reviewer_a_status: str = "not_started"
    reviewer_a_started_at: str | None = None
    reviewer_a_completed_at: str | None = None
    reviewer_a_notes: str = ""
    reviewer_a_verdict: str = ""
    reviewer_a_plan_signature: str = ""
    reviewer_b_status: str = "not_started"
    reviewer_b_started_at: str | None = None
    reviewer_b_completed_at: str | None = None
    reviewer_b_notes: str = ""
    reviewer_b_decision: str = ""
    reviewer_b_plan_signature: str = ""
    replan_required: bool = False
    next_cycle_prompt: str = ""
    closeout_status: str = "not_started"
    closeout_title: str = "Closeout"
    closeout_display_description: str = "Closeout"
    closeout_codex_description: str = "Closeout"
    closeout_success_criteria: str = "Closeout"
    closeout_deadline_at: str = ""
    closeout_reasoning_effort: str = "high"
    closeout_model_provider: str = ""
    closeout_model: str = ""
    closeout_parallel_group: str = ""
    closeout_depends_on: list[str] = field(default_factory=list)
    closeout_owned_paths: list[str] = field(default_factory=lambda: ["README.md", "docs/CLOSEOUT_REPORT.md"])
    closeout_notes: str = ""
    closeout_started_at: str | None = None
    closeout_completed_at: str | None = None
    closeout_commit_hash: str | None = None
    steps: list[ExecutionStep] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionPlanState":
        raw_steps = data.get("steps", data.get("tasks", []))
        steps = []
        if isinstance(raw_steps, list):
            for item in raw_steps:
                if isinstance(item, dict):
                    steps.append(ExecutionStep.from_dict(item))
        return cls(
            plan_title=str(data.get("plan_title", data.get("title", ""))).strip(),
            project_prompt=str(data.get("project_prompt", "")).strip(),
            summary=str(data.get("summary", "")).strip(),
            workflow_mode=str(data.get("workflow_mode", "standard")).strip().lower() or "standard",
            execution_mode="parallel",
            default_test_command=str(data.get("default_test_command", "python -m pytest")).strip() or "python -m pytest",
            last_updated_at=data.get("last_updated_at"),
            reviewer_a_status=str(data.get("reviewer_a_status", "not_started")).strip() or "not_started",
            reviewer_a_started_at=data.get("reviewer_a_started_at"),
            reviewer_a_completed_at=data.get("reviewer_a_completed_at"),
            reviewer_a_notes=str(data.get("reviewer_a_notes", "")).strip(),
            reviewer_a_verdict=str(data.get("reviewer_a_verdict", "")).strip(),
            reviewer_a_plan_signature=str(data.get("reviewer_a_plan_signature", "")).strip(),
            reviewer_b_status=str(data.get("reviewer_b_status", "not_started")).strip() or "not_started",
            reviewer_b_started_at=data.get("reviewer_b_started_at"),
            reviewer_b_completed_at=data.get("reviewer_b_completed_at"),
            reviewer_b_notes=str(data.get("reviewer_b_notes", "")).strip(),
            reviewer_b_decision=str(data.get("reviewer_b_decision", "")).strip(),
            reviewer_b_plan_signature=str(data.get("reviewer_b_plan_signature", "")).strip(),
            replan_required=bool(data.get("replan_required", False)),
            next_cycle_prompt=str(data.get("next_cycle_prompt", "")).strip(),
            closeout_status=str(data.get("closeout_status", "not_started")).strip() or "not_started",
            closeout_title=str(data.get("closeout_title", "Closeout")).strip() or "Closeout",
            closeout_display_description=str(data.get("closeout_display_description", "Closeout")).strip() or "Closeout",
            closeout_codex_description=str(data.get("closeout_codex_description", "Closeout")).strip() or "Closeout",
            closeout_success_criteria=str(data.get("closeout_success_criteria", "Closeout")).strip() or "Closeout",
            closeout_deadline_at=str(data.get("closeout_deadline_at", "")).strip(),
            closeout_reasoning_effort=str(data.get("closeout_reasoning_effort", "high")).strip() or "high",
            closeout_model_provider=str(data.get("closeout_model_provider", "")).strip().lower(),
            closeout_model=str(data.get("closeout_model", "")).strip().lower(),
            closeout_parallel_group=str(data.get("closeout_parallel_group", "")).strip(),
            closeout_depends_on=_string_list(data.get("closeout_depends_on", [])),
            closeout_owned_paths=_string_list(data.get("closeout_owned_paths", ["README.md", "docs/CLOSEOUT_REPORT.md"]))
            or ["README.md", "docs/CLOSEOUT_REPORT.md"],
            closeout_notes=str(data.get("closeout_notes", "")).strip(),
            closeout_started_at=data.get("closeout_started_at"),
            closeout_completed_at=data.get("closeout_completed_at"),
            closeout_commit_hash=data.get("closeout_commit_hash"),
            steps=steps,
        )


@dataclass(slots=True)
class MLExperimentRecord:
    experiment_id: str
    cycle_index: int = 1
    step_id: str = ""
    status: str = "planned"
    title: str = ""
    experiment_kind: str = ""
    dataset_policy: str = ""
    leakage_guard: str = ""
    feature_spec: str = ""
    model_spec: str = ""
    architecture_spec: str = ""
    parameter_budget: str = ""
    resource_budget: str = ""
    train_command: str = ""
    eval_command: str = ""
    primary_metric: str = ""
    metric_direction: str = "maximize"
    metric_value: float | None = None
    validation_summary: str = ""
    artifact_paths: list[str] = field(default_factory=list)
    notes: str = ""
    report_path: str = ""
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MLExperimentRecord":
        return cls(
            experiment_id=str(data.get("experiment_id", data.get("step_id", ""))).strip() or "EXP-UNKNOWN",
            cycle_index=_int_or_default(data.get("cycle_index", 1), 1, minimum=1),
            step_id=str(data.get("step_id", "")).strip(),
            status=str(data.get("status", "planned")).strip() or "planned",
            title=str(data.get("title", "")).strip(),
            experiment_kind=str(data.get("experiment_kind", "")).strip(),
            dataset_policy=str(data.get("dataset_policy", "")).strip(),
            leakage_guard=str(data.get("leakage_guard", "")).strip(),
            feature_spec=str(data.get("feature_spec", "")).strip(),
            model_spec=str(data.get("model_spec", "")).strip(),
            architecture_spec=str(data.get("architecture_spec", "")).strip(),
            parameter_budget=str(data.get("parameter_budget", "")).strip(),
            resource_budget=str(data.get("resource_budget", "")).strip(),
            train_command=str(data.get("train_command", "")).strip(),
            eval_command=str(data.get("eval_command", "")).strip(),
            primary_metric=str(data.get("primary_metric", "")).strip(),
            metric_direction=str(data.get("metric_direction", "maximize")).strip() or "maximize",
            metric_value=_float_or_none(data.get("metric_value")),
            validation_summary=str(data.get("validation_summary", "")).strip(),
            artifact_paths=_string_list(data.get("artifact_paths", [])),
            notes=str(data.get("notes", "")).strip(),
            report_path=str(data.get("report_path", "")).strip(),
            updated_at=data.get("updated_at"),
        )


@dataclass(slots=True)
class MLModeState:
    workflow_mode: str = "standard"
    cycle_index: int = 0
    max_cycles: int = 1
    objective: str = ""
    target_metric: str = ""
    target_value: float | None = None
    metric_direction: str = "maximize"
    stop_requested: bool = False
    stop_reason: str = ""
    replan_required: bool = False
    next_cycle_prompt: str = ""
    best_experiment_id: str = ""
    best_metric_name: str = ""
    best_metric_value: float | None = None
    updated_at: str | None = None
    experiments: list[MLExperimentRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MLModeState":
        raw_experiments = data.get("experiments", [])
        experiments: list[MLExperimentRecord] = []
        if isinstance(raw_experiments, list):
            for item in raw_experiments:
                if isinstance(item, dict):
                    experiments.append(MLExperimentRecord.from_dict(item))
        return cls(
            workflow_mode=str(data.get("workflow_mode", "standard")).strip().lower() or "standard",
            cycle_index=_int_or_default(data.get("cycle_index", 0), 0, minimum=0),
            max_cycles=_int_or_default(data.get("max_cycles", 1), 1, minimum=1),
            objective=str(data.get("objective", "")).strip(),
            target_metric=str(data.get("target_metric", "")).strip(),
            target_value=_float_or_none(data.get("target_value")),
            metric_direction=str(data.get("metric_direction", "maximize")).strip() or "maximize",
            stop_requested=bool(data.get("stop_requested", False)),
            stop_reason=str(data.get("stop_reason", "")).strip(),
            replan_required=bool(data.get("replan_required", False)),
            next_cycle_prompt=str(data.get("next_cycle_prompt", "")).strip(),
            best_experiment_id=str(data.get("best_experiment_id", "")).strip(),
            best_metric_name=str(data.get("best_metric_name", "")).strip(),
            best_metric_value=_float_or_none(data.get("best_metric_value")),
            updated_at=data.get("updated_at"),
            experiments=experiments,
        )
