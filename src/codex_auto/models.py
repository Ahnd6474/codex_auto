from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any


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


@dataclass(slots=True)
class RuntimeOptions:
    model: str = "gpt-5.4"
    effort: str = "medium"
    extra_prompt: str = ""
    init_plan_prompt: str = ""
    approval_mode: str = "never"
    sandbox_mode: str = "workspace-write"
    test_cmd: str = "python -m pytest"
    max_blocks: int = 1
    allow_push: bool = False
    codex_path: str = "codex.cmd"
    git_user_name: str = "codex-auto-bot"
    git_user_email: str = "codex-auto@example.invalid"
    no_progress_limit: int = 3
    regression_limit: int = 3
    empty_cycle_limit: int = 3
    checkpoint_interval_blocks: int = 2
    require_checkpoint_approval: bool = True

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
    display_name: str | None = None
    origin_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)


@dataclass(slots=True)
class LoopCounters:
    no_progress_blocks: int = 0
    regression_failures: int = 0
    empty_cycles: int = 0


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
    long_term_plan_locked: bool = True
    stop_reason: str | None = None
    stop_requested: bool = False
    current_checkpoint_id: str | None = None
    pending_checkpoint_approval: bool = False
    counters: LoopCounters = field(default_factory=LoopCounters)

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
    metadata_file: Path
    project_config_file: Path
    loop_state_file: Path
    long_term_plan_file: Path
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
    checkpoint_state_file: Path
    execution_plan_file: Path
    execution_flow_svg_file: Path
    closeout_report_file: Path

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)


@dataclass(slots=True)
class ProjectContext:
    metadata: RepoMetadata
    runtime: RuntimeOptions
    paths: ProjectPaths
    loop_state: LoopState


@dataclass(slots=True)
class CandidateTask:
    candidate_id: str
    title: str
    rationale: str
    long_term_refs: list[str]
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

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)


@dataclass(slots=True)
class Checkpoint:
    checkpoint_id: str
    title: str
    long_term_refs: list[str]
    target_block: int
    status: str = "pending"
    created_at: str | None = None
    reached_at: str | None = None
    approved_at: str | None = None
    review_notes: str = ""
    commit_hashes: list[str] = field(default_factory=list)
    pushed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)


@dataclass(slots=True)
class ExecutionStep:
    step_id: str
    title: str
    display_description: str = ""
    codex_description: str = ""
    test_command: str = ""
    success_criteria: str = ""
    status: str = "pending"
    started_at: str | None = None
    completed_at: str | None = None
    commit_hash: str | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionStep":
        legacy_description = str(data.get("description", "")).strip()
        display_description = str(data.get("display_description", "")).strip() or legacy_description
        codex_description = str(data.get("codex_description", "")).strip() or legacy_description or display_description
        return cls(
            step_id=str(data.get("step_id", "")).strip() or "LT1",
            title=str(data.get("title", data.get("task_title", ""))).strip(),
            display_description=display_description,
            codex_description=codex_description,
            test_command=str(data.get("test_command", "")).strip(),
            success_criteria=str(data.get("success_criteria", "")).strip(),
            status=str(data.get("status", "pending")).strip() or "pending",
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            commit_hash=data.get("commit_hash"),
            notes=str(data.get("notes", "")).strip(),
        )


@dataclass(slots=True)
class ExecutionPlanState:
    plan_title: str = ""
    project_prompt: str = ""
    summary: str = ""
    default_test_command: str = "python -m pytest"
    last_updated_at: str | None = None
    closeout_status: str = "not_started"
    closeout_started_at: str | None = None
    closeout_completed_at: str | None = None
    closeout_commit_hash: str | None = None
    closeout_notes: str = ""
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
            default_test_command=str(data.get("default_test_command", "python -m pytest")).strip() or "python -m pytest",
            last_updated_at=data.get("last_updated_at"),
            closeout_status=str(data.get("closeout_status", "not_started")).strip() or "not_started",
            closeout_started_at=data.get("closeout_started_at"),
            closeout_completed_at=data.get("closeout_completed_at"),
            closeout_commit_hash=data.get("closeout_commit_hash"),
            closeout_notes=str(data.get("closeout_notes", "")).strip(),
            steps=steps,
        )
