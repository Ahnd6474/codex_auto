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
