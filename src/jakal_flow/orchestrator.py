from __future__ import annotations

from collections.abc import Callable
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from time import perf_counter

from .commit_naming import build_commit_descriptor, build_initial_commit_descriptor, build_setup_commit_descriptor
from .contract_wave import (
    current_spine_version,
    ensure_contract_wave_artifacts,
    load_lineage_manifests,
    manifest_summary_markdown,
    normalize_execution_step_policy,
    policy_summary,
)
from .environment import ensure_gitignore, ensure_virtualenv
from . import execution_plan_support
from .codex_runner import CodexRunner
from .errors import (
    AgentPassExecutionError,
    ExecutionFailure,
    ExecutionPreflightError,
    HANDLED_OPERATION_EXCEPTIONS,
    ParallelExecutionFailure,
    ParallelMergeConflictError,
    VerificationTestFailure,
    execution_failure_from_reason,
    failure_log_fields,
)
from .execution_control import ImmediateStopRequested
from .git_ops import GitCommandError, GitOps
from .memory import MemoryStore
from .model_providers import effective_local_model_provider, normalize_billing_mode, provider_preset, provider_supports_auto_model
from .provider_fallbacks import (
    build_provider_fallback_runtimes,
    is_provider_fallbackable_error,
    is_quota_exhaustion_error,
)
from .model_selection import normalize_reasoning_effort
from .models import CandidateTask, Checkpoint, CodexRunResult, ExecutionPlanState, ExecutionStep, LineageState, LoopState, MLExperimentRecord, MLModeState, ProjectContext, ProjectPaths, RepoMetadata, RuntimeOptions, TestRunResult
from .optimization import scan_optimization_candidates
from .planning_heuristics import assess_direct_execution_bypass
from .parallel_resources import normalize_parallel_worker_mode
from .platform_defaults import default_codex_path
from .planning import (
    FINALIZATION_PROMPT_FILENAME,
    PlanItem,
    attempt_history_entry,
    assess_repository_maturity,
    build_direct_execution_plan,
    build_fast_planner_outline,
    build_mid_term_plan,
    build_mid_term_plan_from_plan_items,
    build_mid_term_plan_from_user_items,
    build_checkpoint_timeline,
    bootstrap_plan_prompt,
    candidate_tasks_from_mid_term,
    checkpoint_timeline_markdown,
    debugger_prompt,
    execution_plan_markdown,
    execution_steps_to_plan_items,
    finalization_prompt,
    ensure_scope_guard,
    generate_project_plan,
    implementation_prompt,
    is_plan_markdown,
    load_debugger_prompt_template,
    load_merger_prompt_template,
    load_plan_decomposition_prompt_template,
    load_plan_generation_prompt_template,
    parse_execution_plan_response,
    prompt_to_plan_decomposition_prompt,
    parse_work_breakdown_response,
    prompt_to_execution_plan_prompt,
    optimization_prompt,
    reflection_markdown,
    reconcile_checkpoint_items_from_blocks,
    scan_repository_inputs,
    select_candidate,
    load_step_execution_prompt_template,
    merger_prompt,
    validate_mid_term_subset,
    work_breakdown_prompt,
    write_active_task,
    load_source_prompt_template,
)
from .reporting import Reporter
from .run_control import immediate_stop_requested
from .status_views import status_from_plan_state
from .step_models import normalize_step_model, normalize_step_model_provider, provider_execution_preflight_error, resolve_step_model_choice
from .utils import (
    append_jsonl,
    compact_text,
    ensure_dir,
    normalize_workflow_mode,
    now_utc_iso,
    read_json,
    read_jsonl,
    read_jsonl_tail,
    read_text,
    svg_text_element,
    wrap_svg_text,
    write_json,
    write_json_if_changed,
    write_text,
    write_text_if_changed,
)
from .verification import VerificationRunner
from .workspace import WorkspaceManager
from .orchestrator_lineage import OrchestratorLineageMixin
from .orchestrator_closeout import OrchestratorCloseoutMixin
from .orchestrator_ml import OrchestratorMlMixin
from .orchestrator_parallel import OrchestratorParallelMixin
from .orchestrator_recovery import OrchestratorRecoveryMixin
from .orchestrator_review import OrchestratorReviewMixin

UTC = getattr(datetime, "UTC", timezone.utc)


class Orchestrator(
    OrchestratorParallelMixin,
    OrchestratorLineageMixin,
    OrchestratorReviewMixin,
    OrchestratorCloseoutMixin,
    OrchestratorMlMixin,
    OrchestratorRecoveryMixin,
):
    _STALE_CLOSEOUT_TIMEOUT = timedelta(hours=6)
    _DEBUGGER_INFRASTRUCTURE_FAILURE_MARKERS = (
        "command not found",
        "is not recognized as the name of a cmdlet",
        "no such file or directory",
        "pytest: error",
        "error: file or directory not found",
        "collected 0 items",
        "no tests ran",
        "modulenotfounderror: no module named 'pytest'",
    )
    _VERIFICATION_INFRASTRUCTURE_PATTERNS = (
        ("verification_infrastructure_failure", r"permission denied", "Verification infrastructure reported a permission error."),
        ("verification_infrastructure_failure", r"not recognized as the name of a cmdlet", "Verification infrastructure could not launch a required command."),
        ("verification_infrastructure_failure", r"modulenotfounderror:\s*no module named ['\"]pytest['\"]", "Verification environment is missing pytest."),
        ("verification_infrastructure_failure", r"pytest:\s*error", "Verification command invocation is invalid."),
        ("verification_infrastructure_failure", r"error:\s*file or directory not found", "Verification command referenced a missing file."),
        (
            "verification_infrastructure_failure",
            r"(?:(?:bash|python(?:3)?|pytest|make|git|uv|gcc|g\+\+|cargo|npm|node|qemu|grade-lab[^\s:]*)[^\n]*(?:command not found|no such file or directory)|(?:command not found|no such file or directory)[^\n]*(?:bash|python(?:3)?|pytest|make|git|uv|gcc|g\+\+|cargo|npm|node|qemu|grade-lab[^\s:]*))",
            "Verification infrastructure could not locate a required tool.",
        ),
    )
    _VERIFICATION_FAILURE_PATTERNS = (
        ("verification_test_failed", r":\s*fail\b", "Verification output reported a failing test."),
        ("verification_test_failed", r"\bsome tests failed\b", "Verification output reported failing tests."),
        ("verification_test_failed", r"\bfailed\b", "Verification output reported a failure."),
        ("verification_test_failed", r"\bmissing '\^", "Verification output reported a missing expected assertion."),
        ("verification_test_failed", r"\btimeout!\s*running\b", "Verification output reported a timeout."),
        ("verification_test_failed", r"\bunexpected scause\b", "Verification output reported a runtime trap."),
        ("verification_test_failed", r"\bsegmentation fault\b", "Verification output reported a segmentation fault."),
        ("verification_test_failed", r"\btraceback \(most recent call last\)", "Verification output reported a Python traceback."),
        ("verification_test_failed", r"\bpanic:", "Verification output reported a panic."),
        ("verification_test_failed", r"\bassert(?:ion)?error\b", "Verification output reported an assertion failure."),
        ("verification_test_failed", r"make:\s*\*\*\*", "Verification output reported a build failure."),
        ("verification_test_failed", r"\bfatal error:", "Verification output reported a fatal build error."),
        ("verification_test_failed", r"\bcannot read [^\n]+", "Verification output reported a missing required artifact."),
    )
    _HOUSEKEEPING_PATHS = frozenset(
        {
            ".gitignore",
            "jakal-flow-logs",
        }
    )

    def __init__(self, workspace_root: Path) -> None:
        self.workspace = WorkspaceManager(workspace_root)
        self.git = GitOps()
        self.verification = VerificationRunner()
        self._execution_plan_state_cache: dict[str, tuple[tuple[object, ...], ExecutionPlanState]] = {}
        self._static_plan_artifact_signature_cache: dict[str, tuple[object, ...]] = {}
        self._state_lock = RLock()

    @staticmethod
    def _plan_state_content_signature(state: ExecutionPlanState) -> str:
        payload = state.to_dict()
        payload.pop("last_updated_at", None)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def _create_codex_runner(self, codex_path: Path | str) -> CodexRunner:
        return CodexRunner(codex_path)

    @staticmethod
    def _path_cache_token(path: Path) -> tuple[int, int, int]:
        try:
            stat_result = path.stat()
        except OSError:
            return (0, 0, 0)
        return (1, int(stat_result.st_mtime_ns), int(stat_result.st_size))

    def _execution_plan_cache_key(self, context: ProjectContext) -> str:
        return str(context.paths.project_root.resolve())

    def _execution_plan_cache_signature(self, context: ProjectContext) -> tuple[object, ...]:
        return (
            self._path_cache_token(context.paths.execution_plan_file),
            str(context.runtime.workflow_mode or "").strip(),
            str(context.runtime.execution_mode or "").strip(),
            str(context.runtime.test_cmd or "").strip(),
            str(context.runtime.effort or "").strip(),
        )

    def _cache_execution_plan_state(self, context: ProjectContext, state: ExecutionPlanState) -> None:
        with self._state_lock:
            self._execution_plan_state_cache[self._execution_plan_cache_key(context)] = (
                self._execution_plan_cache_signature(context),
                deepcopy(state),
            )

    def _scan_repository_inputs(self, context: ProjectContext, *, force_refresh: bool = False) -> dict[str, str]:
        return scan_repository_inputs(
            context.paths.repo_dir,
            cache_file=context.paths.planning_inputs_cache_file,
            force_refresh=force_refresh,
        )

    def _log_planning_metric(
        self,
        context: ProjectContext,
        stage: str,
        *,
        started_at: float,
        flow: str = "planning",
        details: dict[str, object] | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "generated_at": now_utc_iso(),
            "flow": flow,
            "stage": stage,
            "duration_ms": round((perf_counter() - started_at) * 1000.0, 3),
            "block_index": max(0, context.loop_state.block_index),
            "repo_id": context.metadata.repo_id,
            "repo_slug": context.metadata.slug,
        }
        if details:
            payload.update(details)
        append_jsonl(context.paths.planning_metrics_file, payload)

    @staticmethod
    def _step_static_artifact_signature(step: ExecutionStep) -> str:
        payload = step.to_dict()
        for transient_key in ("status", "started_at", "completed_at", "commit_hash", "notes"):
            payload.pop(transient_key, None)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _normalize_reviewer_a_verdict(value: object) -> str:
        normalized = str(value or "").strip().upper()
        if normalized in {"READY", "READY_TO_EXECUTE", "EXECUTION_READY"}:
            return "READY_TO_EXECUTE"
        if normalized == "REPLAN":
            return "REPLAN"
        return ""

    @staticmethod
    def _normalize_reviewer_b_decision(value: object) -> str:
        normalized = str(value or "").strip().upper()
        if normalized in {"SHIP", "READY"}:
            return "SHIP"
        if normalized == "REPLAN":
            return "REPLAN"
        return ""

    def _plan_review_signature(self, plan_state: ExecutionPlanState) -> str:
        payload = {
            "plan_title": str(plan_state.plan_title or "").strip(),
            "project_prompt": str(plan_state.project_prompt or "").strip(),
            "summary": str(plan_state.summary or "").strip(),
            "workflow_mode": normalize_workflow_mode(plan_state.workflow_mode),
            "execution_mode": self._normalize_execution_mode(plan_state.execution_mode),
            "default_test_command": str(plan_state.default_test_command or "").strip(),
            "steps": [self._step_static_artifact_signature(step) for step in plan_state.steps],
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _step_trace_label(step: ExecutionStep) -> str:
        metadata = step.metadata if isinstance(step.metadata, dict) else {}
        block_id = str(metadata.get("candidate_block_id", "")).strip()
        if block_id:
            return f"{step.step_id} (block {block_id})"
        return step.step_id

    def _static_plan_artifact_signature(self, context: ProjectContext, state: ExecutionPlanState) -> tuple[object, ...]:
        return (
            context.metadata.repo_url,
            context.metadata.branch,
            context.metadata.display_name,
            context.metadata.slug,
            state.plan_title.strip(),
            state.project_prompt.strip(),
            state.summary.strip(),
            normalize_workflow_mode(state.workflow_mode),
            self._normalize_execution_mode(state.execution_mode),
            state.default_test_command.strip(),
            tuple(self._step_static_artifact_signature(step) for step in state.steps),
        )

    def _static_plan_artifacts_need_refresh(self, context: ProjectContext, signature: tuple[object, ...]) -> bool:
        cache_key = self._execution_plan_cache_key(context)
        cached_signature = self._static_plan_artifact_signature_cache.get(cache_key)
        if cached_signature != signature:
            return True
        return not all(
            path.exists()
            for path in (
                context.paths.plan_file,
                context.paths.mid_term_plan_file,
                context.paths.scope_guard_file,
            )
        )

    def _save_execution_plan_static_artifacts(self, context: ProjectContext, state: ExecutionPlanState) -> None:
        write_text_if_changed(
            context.paths.plan_file,
            execution_plan_markdown(
                context,
                state.plan_title,
                state.project_prompt,
                state.summary,
                state.workflow_mode,
                state.execution_mode,
                state.steps,
            ),
        )
        mid_term_text, _ = build_mid_term_plan_from_plan_items(
            execution_steps_to_plan_items(state.steps),
            "This plan is the user-reviewed execution sequence for the current local project.",
        )
        write_text_if_changed(context.paths.mid_term_plan_file, mid_term_text)
        write_text_if_changed(context.paths.scope_guard_file, ensure_scope_guard(context))

    def _save_execution_plan_runtime_artifacts(self, context: ProjectContext, state: ExecutionPlanState) -> None:
        checkpoints = self._checkpoints_from_execution_steps(state.steps)
        write_json_if_changed(context.paths.checkpoint_state_file, {"checkpoints": [checkpoint.to_dict() for checkpoint in checkpoints]})
        write_text_if_changed(context.paths.checkpoint_timeline_file, checkpoint_timeline_markdown(checkpoints))

    def _block_plan_cache_signature(
        self,
        context: ProjectContext,
        *,
        plan_text: str,
        max_items: int,
        repo_inputs: dict[str, str] | None,
        work_items: list[str] | None,
    ) -> dict[str, object]:
        return {
            "repo_dir": str(context.paths.repo_dir.resolve()),
            "plan_hash": compact_text(plan_text, 12000),
            "work_items": list(work_items or []),
            "repo_inputs": repo_inputs if isinstance(repo_inputs, dict) else {},
            "plan_file": self._path_cache_token(context.paths.plan_file),
            "execution_plan_file": self._path_cache_token(context.paths.execution_plan_file),
        }

    def _load_cached_block_plan(
        self,
        context: ProjectContext,
        *,
        plan_text: str,
        max_items: int,
        repo_inputs: dict[str, str] | None,
        work_items: list[str] | None,
    ) -> tuple[list, str] | None:
        cached = read_json(context.paths.block_plan_cache_file, default=None)
        if not isinstance(cached, dict):
            return None
        cached_version = int(cached.get("version", 0) or 0)
        if cached_version not in {2, 3}:
            return None
        signature = self._block_plan_cache_signature(
            context,
            plan_text=plan_text,
            max_items=max_items,
            repo_inputs=repo_inputs,
            work_items=work_items,
        )
        if str(cached.get("signature", "")).strip() != json.dumps(signature, ensure_ascii=False, sort_keys=True):
            return None
        block_offset = max(0, int(context.loop_state.block_index or 0) - 1)
        if cached_version >= 3:
            prefetched_blocks = cached.get("prefetched_blocks", [])
            if isinstance(prefetched_blocks, list):
                for prefetched in prefetched_blocks:
                    if not isinstance(prefetched, dict):
                        continue
                    if int(prefetched.get("block_offset", -1) or -1) != block_offset:
                        continue
                    prefetched_text = str(prefetched.get("mid_term_text", "")).strip()
                    prefetched_items = prefetched.get("items", [])
                    parsed_prefetched_items: list[PlanItem] = []
                    if isinstance(prefetched_items, list):
                        for item in prefetched_items:
                            if isinstance(item, dict):
                                item_id = str(item.get("item_id", "")).strip()
                                text = str(item.get("text", "")).strip()
                                if item_id and text:
                                    parsed_prefetched_items.append(PlanItem(item_id=item_id, text=text))
                    if prefetched_text and parsed_prefetched_items:
                        return parsed_prefetched_items, prefetched_text
        mid_term_text = str(cached.get("mid_term_text", ""))
        raw_items = cached.get("items", [])
        if not mid_term_text or not isinstance(raw_items, list):
            return None
        parsed_items: list[PlanItem] = []
        for item in raw_items:
            if isinstance(item, dict):
                item_id = str(item.get("item_id", "")).strip()
                text = str(item.get("text", "")).strip()
                if item_id and text:
                    parsed_items.append(PlanItem(item_id=item_id, text=text))
        if not parsed_items:
            return None
        remaining_items = parsed_items[block_offset:]
        if not remaining_items:
            return None
        selected_items = remaining_items[: max(1, max_items)]
        if block_offset == 0 and len(selected_items) == len(parsed_items) and mid_term_text.strip():
            return selected_items, mid_term_text
        description = str(cached.get("description", "")).strip() or (
            "This plan is regenerated only at block boundaries and must remain a strict subset of the saved project plan."
        )
        rebuilt_mid_term_text, rebuilt_items = build_mid_term_plan_from_plan_items(selected_items, description)
        return rebuilt_items, rebuilt_mid_term_text
        return None

    @staticmethod
    def _serialize_plan_items(items: list[PlanItem]) -> list[dict[str, str]]:
        return [
            {
                "item_id": str(getattr(item, "item_id", "")).strip(),
                "text": str(getattr(item, "text", "")).strip(),
            }
            for item in items
            if str(getattr(item, "item_id", "")).strip() and str(getattr(item, "text", "")).strip()
        ]

    def _prefetched_block_plan_windows(
        self,
        context: ProjectContext,
        *,
        mid_items: list[PlanItem],
        description: str,
        window_count: int = 2,
    ) -> list[dict[str, object]]:
        current_offset = max(0, int(context.loop_state.block_index or 0) - 1)
        prefetched_blocks: list[dict[str, object]] = []
        for relative_offset in range(1, max(1, window_count) + 1):
            block_offset = current_offset + relative_offset
            remaining_items = mid_items[block_offset:]
            if not remaining_items:
                break
            prefetched_text, prefetched_items = build_mid_term_plan_from_plan_items(remaining_items, description)
            serialized_items = self._serialize_plan_items(prefetched_items)
            if not prefetched_text.strip() or not serialized_items:
                continue
            prefetched_blocks.append(
                {
                    "block_offset": block_offset,
                    "mid_term_text": prefetched_text,
                    "items": serialized_items,
                }
            )
        return prefetched_blocks

    def _store_block_plan_cache(
        self,
        context: ProjectContext,
        *,
        plan_text: str,
        max_items: int,
        repo_inputs: dict[str, str] | None,
        work_items: list[str] | None,
        mid_items: list,
        mid_term_text: str,
        description: str,
    ) -> None:
        signature = self._block_plan_cache_signature(
            context,
            plan_text=plan_text,
            max_items=max_items,
            repo_inputs=repo_inputs,
            work_items=work_items,
        )
        serialized_items = self._serialize_plan_items(mid_items)
        write_json_if_changed(
            context.paths.block_plan_cache_file,
            {
                "version": 3,
                "signature": json.dumps(signature, ensure_ascii=False, sort_keys=True),
                "description": description,
                "mid_term_text": mid_term_text,
                "items": serialized_items,
                "prefetched_blocks": self._prefetched_block_plan_windows(
                    context,
                    mid_items=mid_items,
                    description=description,
                ),
            },
        )

    def _step_metadata_copy(self, step: ExecutionStep) -> dict[str, object]:
        return deepcopy(step.metadata) if isinstance(step.metadata, dict) else {}

    def _set_step_failure_metadata(self, step: ExecutionStep, error: BaseException | None) -> None:
        metadata = self._step_metadata_copy(step)
        metadata.update(failure_log_fields(error))
        step.metadata = metadata

    def _clear_step_failure_metadata(self, step: ExecutionStep) -> None:
        metadata = self._step_metadata_copy(step)
        metadata.pop("failure_type", None)
        metadata.pop("failure_reason_code", None)
        step.metadata = metadata

    def _set_step_failure_from_worker_result(self, step: ExecutionStep, worker_result: dict[str, object]) -> None:
        reason_code = str(worker_result.get("failure_reason_code") or "").strip() or None
        summary = str(worker_result.get("test_summary") or worker_result.get("notes") or "").strip() or "Parallel worker failed."
        failure = execution_failure_from_reason(reason_code, summary)
        failure_type = str(worker_result.get("failure_type") or "").strip()
        if failure_type and not reason_code:
            failure = ExecutionFailure(summary, reason_code=failure.reason_code)
        self._set_step_failure_metadata(step, failure)

    def _resolve_local_repo_backend(self, repo_dir: Path, preferred: str = "auto") -> str:
        normalized = str(preferred or "auto").strip().lower() or "auto"
        if self.git.is_git_repository(repo_dir):
            return "git"
        if self.git.is_lit_repository(repo_dir):
            return "lit"
        if normalized in {"git", "lit"}:
            return normalized
        return "git"

    def setup_local_project(
        self,
        project_dir: Path,
        runtime: RuntimeOptions,
        branch: str = "main",
        origin_url: str = "",
        display_name: str = "",
        repo_id: str = "",
    ) -> ProjectContext:
        runtime.execution_mode = self._normalize_execution_mode(runtime.execution_mode)
        resolved_dir = project_dir.resolve()
        repo_backend = self._resolve_local_repo_backend(resolved_dir, preferred=getattr(runtime, "repo_backend", "auto"))
        runtime.repo_backend = repo_backend
        created_repo = self.git.ensure_repository(resolved_dir, branch, backend=repo_backend)
        active_branch = self.git.current_branch(resolved_dir) or branch or "main"
        if repo_backend == "git" and origin_url.strip():
            self.git.set_remote_url(resolved_dir, "origin", origin_url.strip())
        detected_origin = origin_url.strip() if repo_backend == "lit" else (self.git.remote_url(resolved_dir, "origin") or origin_url.strip())
        if repo_backend == "git":
            self._sync_local_setup_branch_from_origin(resolved_dir, active_branch)

        normalized_repo_id = str(repo_id or "").strip()
        existing = self.workspace.load_project_by_id(normalized_repo_id) if normalized_repo_id else self.workspace.find_project_by_repo_path(resolved_dir)
        if existing is not None and normalized_repo_id:
            conflicting = self.workspace.find_project_by_repo_path(resolved_dir)
            if conflicting is not None and conflicting.metadata.repo_id != existing.metadata.repo_id:
                raise ValueError(f"Working directory is already managed by another project: {resolved_dir}")
        if existing is None:
            context = self.workspace.initialize_local_project(
                project_dir=resolved_dir,
                branch=active_branch,
                runtime=runtime,
                origin_url=detected_origin or origin_url.strip(),
                display_name=display_name.strip(),
            )
            context.metadata.vcs_backend = repo_backend
        else:
            context = existing
            context.runtime = runtime
            self.workspace.rebind_local_project_repo_path(context, resolved_dir)
            context.metadata.branch = active_branch
            context.metadata.repo_path = resolved_dir
            context.metadata.repo_url = detected_origin or origin_url.strip() or str(resolved_dir)
            context.metadata.origin_url = detected_origin or origin_url.strip() or None
            context.metadata.repo_kind = "local"
            context.metadata.vcs_backend = repo_backend
            context.metadata.display_name = display_name.strip() or context.metadata.display_name or resolved_dir.name

        self.git.configure_local_identity(
            context.paths.repo_dir,
            runtime.git_user_name,
            runtime.git_user_email,
        )
        ensure_virtualenv(context.paths.repo_dir)
        gitignore_updated = ensure_gitignore(context.paths.repo_dir)
        self._ensure_project_documents(context)

        if created_repo or not self.git.has_commits(context.paths.repo_dir):
            initial_commit = build_initial_commit_descriptor(context)
            safe_revision = self.git.create_initial_commit(
                context.paths.repo_dir,
                initial_commit.message,
                author_name=initial_commit.author_name,
                force=True,
            )
        else:
            safe_revision = self.git.current_revision(context.paths.repo_dir)
            if gitignore_updated:
                changed_after_gitignore = set(self.git.changed_files(context.paths.repo_dir))
                if ".gitignore" in changed_after_gitignore:
                    setup_commit = build_setup_commit_descriptor(context)
                    safe_revision = self.git.commit_paths(
                        context.paths.repo_dir,
                        [".gitignore"],
                        setup_commit.message,
                        author_name=setup_commit.author_name,
                        force=True,
                    )

        context.metadata.branch = self.git.current_branch(context.paths.repo_dir) or active_branch
        if repo_backend == "git":
            self._push_local_setup_branch_to_origin(context.paths.repo_dir, context.metadata.branch)
        context.metadata.current_safe_revision = safe_revision
        context.metadata.current_status = "setup_ready"
        context.metadata.last_run_at = now_utc_iso()
        context.metadata.repo_url = (
            detected_origin or str(context.paths.repo_dir)
            if repo_backend == "lit"
            else (self.git.remote_url(context.paths.repo_dir, "origin") or str(context.paths.repo_dir))
        )
        context.metadata.origin_url = (
            detected_origin or None
            if repo_backend == "lit"
            else self.git.remote_url(context.paths.repo_dir, "origin")
        )
        context.metadata.repo_kind = "local"
        context.metadata.vcs_backend = repo_backend
        context.metadata.display_name = display_name.strip() or context.metadata.display_name or context.paths.repo_dir.name
        context.loop_state.current_safe_revision = safe_revision
        context.loop_state.stop_requested = False
        context.loop_state.stop_reason = None
        self._clear_stale_checkpoint_approval_state(context)
        self.workspace.save_project(context)
        self.save_execution_plan_state(context, self.load_execution_plan_state(context))
        return context

    def setup_transient_local_project(
        self,
        project_dir: Path,
        runtime: RuntimeOptions,
        branch: str = "main",
        origin_url: str = "",
        display_name: str = "",
    ) -> ProjectContext:
        runtime.execution_mode = self._normalize_execution_mode(runtime.execution_mode)
        resolved_dir = project_dir.resolve()
        repo_backend = self._resolve_local_repo_backend(resolved_dir, preferred=getattr(runtime, "repo_backend", "auto"))
        runtime.repo_backend = repo_backend
        if repo_backend == "git" and not self.git.is_git_repository(resolved_dir):
            raise ExecutionPreflightError(
                f"Terminal-Bench integration requires an existing git repository: {resolved_dir}"
            )
        if repo_backend == "lit" and not self.git.is_lit_repository(resolved_dir):
            raise ExecutionPreflightError(
                f"Transient local execution requires an existing lit repository: {resolved_dir}"
            )
        active_branch = self.git.current_branch(resolved_dir) or branch or "main"
        detected_origin = origin_url.strip() if repo_backend == "lit" else (self.git.remote_url(resolved_dir, "origin") or origin_url.strip())

        existing = self.workspace.find_project_by_repo_path(resolved_dir)
        if existing is None:
            context = self.workspace.initialize_local_project(
                project_dir=resolved_dir,
                branch=active_branch,
                runtime=runtime,
                origin_url=detected_origin,
                display_name=display_name.strip(),
                local_logs_mode="workspace",
            )
            context.metadata.vcs_backend = repo_backend
        else:
            context = existing
            context.runtime = runtime
            context.metadata.branch = active_branch
            context.metadata.repo_path = resolved_dir
            context.metadata.repo_url = detected_origin or str(resolved_dir)
            context.metadata.origin_url = detected_origin or None
            context.metadata.repo_kind = "local"
            context.metadata.vcs_backend = repo_backend
            context.metadata.local_logs_mode = "workspace"
            context.metadata.display_name = display_name.strip() or context.metadata.display_name or resolved_dir.name
            context.paths.repo_dir = resolved_dir
            context.paths = self.workspace._apply_workspace_project_log_paths(context.paths)
            ensure_dir(context.paths.logs_dir)

        self._ensure_project_documents(context)
        safe_revision = self.git.current_revision(context.paths.repo_dir)
        context.metadata.branch = active_branch
        context.metadata.current_safe_revision = safe_revision or None
        context.metadata.current_status = "setup_ready"
        context.metadata.last_run_at = now_utc_iso()
        context.metadata.repo_url = detected_origin or str(context.paths.repo_dir)
        context.metadata.origin_url = detected_origin or None
        context.metadata.repo_kind = "local"
        context.metadata.vcs_backend = repo_backend
        context.metadata.local_logs_mode = "workspace"
        context.metadata.display_name = display_name.strip() or context.metadata.display_name or context.paths.repo_dir.name
        context.loop_state.current_safe_revision = safe_revision or None
        context.loop_state.stop_requested = False
        context.loop_state.stop_reason = None
        self._clear_stale_checkpoint_approval_state(context)
        self.workspace.save_project(context)
        self.save_execution_plan_state(context, self.load_execution_plan_state(context))
        return context

    def _sync_local_setup_branch_from_origin(self, repo_dir: Path, branch: str) -> None:
        target_branch = str(branch or "").strip()
        if not target_branch:
            return
        remote_url = self.git.remote_url(repo_dir, "origin")
        if not remote_url:
            return
        try:
            self.git.fetch(repo_dir, "origin", target_branch)
        except GitCommandError:
            return
        remote_head = self.git.remote_branch_revision(repo_dir, "origin", target_branch)
        if not remote_head:
            return
        if not self.git.has_commits(repo_dir) and self.git.has_changes(repo_dir):
            raise ExecutionPreflightError(
                f"Cannot pull origin/{target_branch} into an uncommitted local repository. Commit or clone the remote first."
            )
        try:
            self.git.pull_ff_only(repo_dir, "origin", target_branch)
        except GitCommandError:
            return

    def _push_local_setup_branch_to_origin(self, repo_dir: Path, branch: str) -> None:
        target_branch = str(branch or "").strip()
        if not target_branch:
            return
        remote_url = self.git.remote_url(repo_dir, "origin")
        if not remote_url or not self.git.has_commits(repo_dir):
            return
        local_head = self.git.local_branch_revision(repo_dir, target_branch)
        if not local_head:
            return
        remote_head = self.git.remote_branch_revision(repo_dir, "origin", target_branch)
        if remote_head == local_head:
            return
        try:
            self.git.push(repo_dir, target_branch)
        except GitCommandError:
            return

    def generate_execution_plan(
        self,
        project_dir: Path,
        runtime: RuntimeOptions,
        project_prompt: str,
        branch: str = "main",
        max_steps: int = 6,
        origin_url: str = "",
        progress_callback: Callable[[ProjectContext, str, str, dict[str, object] | None], None] | None = None,
    ) -> tuple[ProjectContext, ExecutionPlanState]:
        context = self.setup_local_project(project_dir=project_dir, runtime=runtime, branch=branch, origin_url=origin_url)
        return self._generate_execution_plan_with_context(
            context=context,
            runtime=runtime,
            project_prompt=project_prompt,
            max_steps=max_steps,
            progress_callback=progress_callback,
        )

    def generate_transient_execution_plan(
        self,
        project_dir: Path,
        runtime: RuntimeOptions,
        project_prompt: str,
        branch: str = "main",
        max_steps: int = 6,
        origin_url: str = "",
        display_name: str = "",
        progress_callback: Callable[[ProjectContext, str, str, dict[str, object] | None], None] | None = None,
    ) -> tuple[ProjectContext, ExecutionPlanState]:
        context = self.setup_transient_local_project(
            project_dir=project_dir,
            runtime=runtime,
            branch=branch,
            origin_url=origin_url,
            display_name=display_name,
        )
        return self._generate_execution_plan_with_context(
            context=context,
            runtime=runtime,
            project_prompt=project_prompt,
            max_steps=max_steps,
            progress_callback=progress_callback,
        )

    def _generate_execution_plan_with_context(
        self,
        *,
        context: ProjectContext,
        runtime: RuntimeOptions,
        project_prompt: str,
        max_steps: int,
        progress_callback: Callable[[ProjectContext, str, str, dict[str, object] | None], None] | None = None,
    ) -> tuple[ProjectContext, ExecutionPlanState]:
        project_prompt = project_prompt.strip()
        previous_plan_state = self.load_execution_plan_state(context)
        workflow_mode = normalize_workflow_mode(runtime.workflow_mode)
        normalized_execution_mode = self._normalize_execution_mode(runtime.execution_mode)
        planning_mode = self._planning_mode(runtime)
        planning_effort = self._resolved_planning_effort(runtime)
        planning_stage_count = 4

        def report_progress(event_type: str, message: str, details: dict[str, object] | None = None) -> None:
            if progress_callback is None:
                return
            progress_callback(
                context,
                event_type,
                message,
                {
                    "flow": "planning",
                    **(details or {}),
                },
            )

        decomposition_prompt_template = load_plan_decomposition_prompt_template(normalized_execution_mode, workflow_mode)
        planning_prompt_template = load_plan_generation_prompt_template(normalized_execution_mode, workflow_mode)
        report_progress(
            "plan-started",
            "Collecting repository context for planning.",
            {
                "stage_key": "context_scan",
                "stage_index": 1,
                "stage_count": planning_stage_count,
                "status": "running",
            },
        )
        context_scan_started_at = perf_counter()
        repo_inputs = self._scan_repository_inputs(context)
        direct_execution_assessment = assess_direct_execution_bypass(
            repo_inputs=repo_inputs,
            project_prompt=project_prompt,
            previous_plan_state=previous_plan_state,
            max_steps=max_steps,
            planning_effort=planning_effort,
            workflow_mode=workflow_mode,
        )
        self._log_planning_metric(
            context,
            "context_scan",
            started_at=context_scan_started_at,
            details={
                "cache_file": str(context.paths.planning_inputs_cache_file),
                "planning_mode": planning_mode,
            },
        )
        skip_full_planning = planning_mode == "no"
        runner = CodexRunner(context.runtime.codex_path)
        plan_title = ""
        summary = ""
        steps: list[ExecutionStep] = []
        skip_planner_a = self._should_skip_planner_decomposition(
            planning_mode,
        )
        planner_outline = ""
        if skip_full_planning:
            report_progress(
                "planner-agent-started",
                "Direct execution bypass is synthesizing a single focused block.",
                {
                    "stage_key": "planner_a",
                    "stage_index": 2,
                    "stage_count": planning_stage_count,
                    "status": "running",
                    "agent_key": "planner_a",
                    "agent_label": "Planner Agent A",
                },
            )
            direct_plan_started_at = perf_counter()
            plan_title, summary, steps, planner_outline = build_direct_execution_plan(
                project_prompt,
                test_command=runtime.test_cmd,
                reasoning_effort=normalize_reasoning_effort(runtime.effort, fallback="high"),
                spine_version=current_spine_version(context.paths),
                step_type=direct_execution_assessment.step_type,
                direct_execution_score=direct_execution_assessment.score,
                direct_execution_reasons=direct_execution_assessment.reasons,
            )
            steps = self._materialize_generated_step_models(steps, runtime)
            self._log_planning_metric(
                context,
                "planner_direct_bypass",
                started_at=direct_plan_started_at,
                details={
                    "step_type": direct_execution_assessment.step_type,
                    "step_count": len(steps),
                    "score": direct_execution_assessment.score,
                    "threshold": direct_execution_assessment.threshold,
                    "reasons": list(direct_execution_assessment.reasons),
                    "positive_markers": list(direct_execution_assessment.positive_markers),
                    "negative_markers": list(direct_execution_assessment.negative_markers),
                },
            )
            report_progress(
                "planner-agent-finished",
                "Planner Agent A was bypassed for a narrow direct-execution request.",
                {
                    "stage_key": "planner_a",
                    "stage_index": 2,
                    "stage_count": planning_stage_count,
                    "status": "completed",
                    "agent_key": "planner_a",
                    "agent_label": "Planner Agent A",
                    "skipped": True,
                    "bypass_reason": "small_task_direct_execution",
                    "score": direct_execution_assessment.score,
                    "planning_mode": planning_mode,
                },
            )
            report_progress(
                "planner-agent-started",
                "Planner Agent B was bypassed because the request was collapsed to one direct execution block.",
                {
                    "stage_key": "planner_b",
                    "stage_index": 3,
                    "stage_count": planning_stage_count,
                    "status": "running",
                    "agent_key": "planner_b",
                    "agent_label": "Planner Agent B",
                },
            )
            report_progress(
                "planner-agent-finished",
                "Planner Agent B was bypassed for a narrow direct-execution request.",
                {
                    "stage_key": "planner_b",
                    "stage_index": 3,
                    "stage_count": planning_stage_count,
                    "status": "completed",
                    "agent_key": "planner_b",
                    "agent_label": "Planner Agent B",
                    "skipped": True,
                    "bypass_reason": "small_task_direct_execution",
                    "score": direct_execution_assessment.score,
                    "planning_mode": planning_mode,
                },
            )
        elif skip_planner_a:
            report_progress(
                "planner-agent-started",
                "Planner Agent A fast lane is synthesizing a compact heuristic outline.",
                {
                    "stage_key": "planner_a",
                    "stage_index": 2,
                    "stage_count": planning_stage_count,
                    "status": "running",
                    "agent_key": "planner_a",
                    "agent_label": "Planner Agent A",
                },
            )
            planner_a_started_at = perf_counter()
            planner_outline = build_fast_planner_outline(
                repo_inputs,
                project_prompt,
                current_spine_version=current_spine_version(context.paths),
            )
            self._log_planning_metric(
                context,
                "planner_a_fast_outline",
                started_at=planner_a_started_at,
                details={"skipped": True},
            )
            report_progress(
                "planner-agent-finished",
                "Planner Agent A was skipped in compact planning mode; a compact heuristic outline was saved instead.",
                {
                    "stage_key": "planner_a",
                    "stage_index": 2,
                    "stage_count": planning_stage_count,
                    "status": "completed",
                    "agent_key": "planner_a",
                    "agent_label": "Planner Agent A",
                    "skipped": True,
                },
            )
        else:
            decomposition_prompt = prompt_to_plan_decomposition_prompt(
                context=context,
                repo_inputs=repo_inputs,
                user_prompt=project_prompt,
                max_steps=max_steps,
                execution_mode=normalized_execution_mode,
                template_text=decomposition_prompt_template,
            )
            planner_a_started_at = perf_counter()
            report_progress(
                "planner-agent-started",
                "Planner Agent A is decomposing the work into implementation blocks.",
                {
                    "stage_key": "planner_a",
                    "stage_index": 2,
                    "stage_count": planning_stage_count,
                    "status": "running",
                    "agent_key": "planner_a",
                    "agent_label": "Planner Agent A",
                },
            )
            decomposition_result = self._run_pass_with_provider_fallback(
                context=context,
                runner=runner,
                prompt=decomposition_prompt,
                pass_type="plan-agent-a-decomposition",
                block_index=max(0, context.loop_state.block_index),
                search_enabled=False,
                reasoning_effort=planning_effort,
            )
            self._log_planning_metric(
                context,
                "planner_a_decomposition",
                started_at=planner_a_started_at,
                details={"returncode": decomposition_result.returncode},
            )
            report_progress(
                "planner-agent-finished",
                "Planner Agent A finished the decomposition outline.",
                {
                    "stage_key": "planner_a",
                    "stage_index": 2,
                    "stage_count": planning_stage_count,
                    "status": "completed" if decomposition_result.returncode == 0 else "failed",
                    "agent_key": "planner_a",
                    "agent_label": "Planner Agent A",
                    "returncode": decomposition_result.returncode,
                },
            )
            planner_outline = (decomposition_result.last_message or "").strip() if decomposition_result.returncode == 0 else ""
        write_text(
            context.paths.docs_dir / "PLAN_AGENT_A_OUTLINE.md",
            planner_outline or "Planner Agent A did not return a reusable decomposition artifact.",
        )
        if not skip_full_planning:
            prompt = prompt_to_execution_plan_prompt(
                context=context,
                repo_inputs=repo_inputs,
                user_prompt=project_prompt,
                max_steps=max_steps,
                execution_mode=normalized_execution_mode,
                planner_outline=planner_outline,
                template_text=planning_prompt_template,
            )
            planner_b_started_at = perf_counter()
            report_progress(
                "planner-agent-started",
                "Planner Agent B is packing the final execution plan.",
                {
                    "stage_key": "planner_b",
                    "stage_index": 3,
                    "stage_count": planning_stage_count,
                    "status": "running",
                    "agent_key": "planner_b",
                    "agent_label": "Planner Agent B",
                },
            )
            result = self._run_pass_with_provider_fallback(
                context=context,
                runner=runner,
                prompt=prompt,
                pass_type="plan-agent-b-packing",
                block_index=max(0, context.loop_state.block_index),
                search_enabled=False,
                reasoning_effort=planning_effort,
            )
            self._log_planning_metric(
                context,
                "planner_b_packing",
                started_at=planner_b_started_at,
                details={"returncode": result.returncode},
            )
            report_progress(
                "planner-agent-finished",
                "Planner Agent B finished the execution plan draft.",
                {
                    "stage_key": "planner_b",
                    "stage_index": 3,
                    "stage_count": planning_stage_count,
                    "status": "completed" if result.returncode == 0 else "failed",
                    "agent_key": "planner_b",
                    "agent_label": "Planner Agent B",
                    "returncode": result.returncode,
                },
            )
            if result.returncode == 0:
                parse_started_at = perf_counter()
                plan_title, summary, steps = parse_execution_plan_response(
                    result.last_message or "",
                    runtime.test_cmd,
                    runtime.effort,
                    limit=max_steps,
                )
                steps = self._postprocess_generated_plan_steps(
                    steps,
                    planner_outline=planner_outline,
                    execution_mode=normalized_execution_mode,
                )
                steps = self._materialize_generated_step_models(steps, runtime)
                self._log_planning_metric(
                    context,
                    "plan_response_parse",
                    started_at=parse_started_at,
                    details={"step_count": len(steps)},
                )
        if not steps:
            steps = [
                ExecutionStep(
                    step_id="ST1",
                    title=project_prompt.strip() or "Implement the requested improvement safely",
                    display_description="Define the first safe implementation checkpoint.",
                    codex_description=project_prompt.strip() or "Implement the requested improvement safely.",
                    test_command=runtime.test_cmd,
                    success_criteria="Run the configured verification command successfully.",
                    reasoning_effort=normalize_reasoning_effort(runtime.effort, fallback="high"),
                )
            ]
            summary = summary or "Fallback execution plan created because Codex did not return a machine-readable breakdown."

        report_progress(
            "plan-finalizing",
            "Validating, post-processing, and saving the execution plan.",
            {
                "stage_key": "finalize",
                "stage_index": 4,
                "stage_count": planning_stage_count,
                "status": "running",
            },
        )
        plan_state = ExecutionPlanState(
            plan_title=plan_title.strip() or context.metadata.display_name or context.metadata.slug,
            project_prompt=project_prompt.strip(),
            summary=summary.strip(),
            workflow_mode=workflow_mode,
            execution_mode=normalized_execution_mode,
            default_test_command=runtime.test_cmd,
            last_updated_at=now_utc_iso(),
            steps=steps,
        )
        finalize_started_at = perf_counter()
        self.save_execution_plan_state(context, plan_state)
        self._log_planning_metric(
            context,
            "plan_finalize",
            started_at=finalize_started_at,
            details={"step_count": len(steps)},
        )
        self._initialize_ml_mode_state(
            context,
            plan_state,
            project_prompt,
            cycle_index=self._suggest_ml_cycle_index(context, previous_plan_state),
        )
        context.metadata.current_status = "plan_ready"
        context.metadata.last_run_at = now_utc_iso()
        self.workspace.save_project(context)
        return context, plan_state

    def _should_skip_planner_decomposition(
        self,
        planning_mode: str,
    ) -> bool:
        return planning_mode == "compact"

    @staticmethod
    def _planning_mode(runtime: RuntimeOptions) -> str:
        normalized = str(getattr(runtime, "planning_mode", "") or "").strip().lower()
        if normalized in {"no", "compact", "full"}:
            return normalized
        return "compact" if bool(getattr(runtime, "use_fast_mode", False)) else "full"

    def _planning_effort_for_runtime(self, runtime: RuntimeOptions, planning_effort: str) -> str:
        selected_provider = str(getattr(runtime, "model_provider", "") or "").strip().lower()
        if selected_provider == "ensemble":
            planning_model = str(
                getattr(runtime, "ensemble_openai_model", "")
                or getattr(runtime, "execution_model", "")
                or getattr(runtime, "model", "")
                or getattr(runtime, "model_slug_input", "")
            ).strip().lower()
        else:
            planning_model = str(
                getattr(runtime, "execution_model", "")
                or getattr(runtime, "model", "")
                or getattr(runtime, "model_slug_input", "")
            ).strip().lower()
        normalized_effort = normalize_reasoning_effort(planning_effort, fallback="high")
        if planning_model != "gpt-5.4":
            return normalized_effort
        effort_ladder = ["low", "medium", "high", "xhigh"]
        current_index = effort_ladder.index(normalized_effort) if normalized_effort in effort_ladder else 1
        return effort_ladder[max(0, current_index - 1)]

    def _resolved_planning_effort(self, runtime: RuntimeOptions) -> str:
        planning_effort = normalize_reasoning_effort(
            getattr(runtime, "planning_effort", ""),
            fallback=normalize_reasoning_effort(runtime.effort, fallback="high"),
        )
        return self._planning_effort_for_runtime(runtime, planning_effort)

    def _postprocess_generated_plan_steps(
        self,
        steps: list[ExecutionStep],
        *,
        planner_outline: str,
        execution_mode: str,
    ) -> list[ExecutionStep]:
        return execution_plan_support.postprocess_generated_plan_steps(
            steps,
            planner_outline=planner_outline,
            execution_mode=execution_mode,
        )

    def _materialize_generated_step_models(
        self,
        steps: list[ExecutionStep],
        runtime: RuntimeOptions,
    ) -> list[ExecutionStep]:
        return execution_plan_support.materialize_generated_step_models(steps, runtime)

    def _coerce_string_list(self, value: object) -> list[str]:
        return execution_plan_support.coerce_string_list(value)

    def _normalize_owned_paths(self, value: object) -> list[str]:
        return execution_plan_support.normalize_owned_paths(value)





































    def load_execution_plan_state(self, context: ProjectContext) -> ExecutionPlanState:
        with self._state_lock:
            cache_key = self._execution_plan_cache_key(context)
            cache_signature = self._execution_plan_cache_signature(context)
            cached = self._execution_plan_state_cache.get(cache_key)
            if cached is not None and cached[0] == cache_signature:
                cached_state = deepcopy(cached[1])
                self._normalize_loaded_execution_plan_state(context, cached_state)
                if not self._closeout_run_is_stale(context, cached_state) and not self._reviewer_a_run_is_stale(context, cached_state):
                    self._cache_execution_plan_state(context, cached_state)
                    return cached_state
            payload = read_json(context.paths.execution_plan_file, default=None)
            if not isinstance(payload, dict):
                state = ExecutionPlanState(
                    workflow_mode=normalize_workflow_mode(context.runtime.workflow_mode),
                    default_test_command=context.runtime.test_cmd,
                    last_updated_at=now_utc_iso(),
                    steps=[],
                )
                self._cache_execution_plan_state(context, state)
                return state
            state = ExecutionPlanState.from_dict(payload)
            self._normalize_loaded_execution_plan_state(context, state)
            self._cache_execution_plan_state(context, state)
            return state

    def _normalize_loaded_execution_plan_state(self, context: ProjectContext, state: ExecutionPlanState) -> None:
        state.workflow_mode = normalize_workflow_mode(state.workflow_mode or context.runtime.workflow_mode)
        state.execution_mode = self._normalize_execution_mode(state.execution_mode or context.runtime.execution_mode)
        if not state.default_test_command:
            state.default_test_command = context.runtime.test_cmd
        if state.execution_mode == "parallel":
            self._reduce_redundant_parallel_dependencies(state.steps)
            self._normalize_hybrid_step_metadata(state.steps)
        fallback_effort = normalize_reasoning_effort(context.runtime.effort, fallback="high")
        for step in state.steps:
            step.reasoning_effort = normalize_reasoning_effort(step.reasoning_effort, fallback=fallback_effort)
        self._recover_stale_reviewer_a_state(context, state)
        self._recover_stale_closeout_state(context, state)

    def update_execution_plan(
        self,
        project_dir: Path,
        runtime: RuntimeOptions,
        plan_state: ExecutionPlanState,
        branch: str = "main",
        origin_url: str = "",
    ) -> tuple[ProjectContext, ExecutionPlanState]:
        context = self.setup_local_project(project_dir=project_dir, runtime=runtime, branch=branch, origin_url=origin_url)
        saved = self.save_execution_plan_state(context, plan_state)
        context.metadata.current_status = self._status_from_plan_state(saved)
        context.metadata.last_run_at = now_utc_iso()
        self.workspace.save_project(context)
        return context, saved

    def save_execution_plan_state(self, context: ProjectContext, plan_state: ExecutionPlanState) -> ExecutionPlanState:
        with self._state_lock:
            execution_mode = self._normalize_execution_mode(plan_state.execution_mode or context.runtime.execution_mode)
            workflow_mode = normalize_workflow_mode(plan_state.workflow_mode or context.runtime.workflow_mode)
            normalized_steps = self._normalize_execution_steps(context, plan_state.steps, plan_state.default_test_command, execution_mode)
            prior_state: ExecutionPlanState | None = None
            cached_entry = self._execution_plan_state_cache.get(self._execution_plan_cache_key(context))
            if cached_entry is not None:
                prior_state = deepcopy(cached_entry[1])
            else:
                payload = read_json(context.paths.execution_plan_file, default=None)
                if isinstance(payload, dict):
                    prior_state = ExecutionPlanState.from_dict(payload)
                    self._normalize_loaded_execution_plan_state(context, prior_state)

            candidate_state = ExecutionPlanState(
                plan_title=plan_state.plan_title.strip() or context.metadata.display_name or context.metadata.slug,
                project_prompt=plan_state.project_prompt.strip(),
                summary=plan_state.summary.strip(),
                workflow_mode=workflow_mode,
                execution_mode=execution_mode,
                default_test_command=plan_state.default_test_command.strip() or context.runtime.test_cmd,
                steps=normalized_steps,
            )
            current_plan_signature = self._plan_review_signature(candidate_state)
            prior_plan_signature = self._plan_review_signature(prior_state) if prior_state is not None else ""
            plan_structure_changed = prior_state is not None and prior_plan_signature != current_plan_signature
            closeout_ready = self._all_steps_completed(normalized_steps)
            closeout_status = plan_state.closeout_status.strip() or "not_started"
            closeout_started_at = plan_state.closeout_started_at
            closeout_completed_at = plan_state.closeout_completed_at
            closeout_commit_hash = plan_state.closeout_commit_hash
            closeout_notes = plan_state.closeout_notes.strip()
            reviewer_a_status = str(plan_state.reviewer_a_status or "not_started").strip().lower() or "not_started"
            reviewer_a_started_at = plan_state.reviewer_a_started_at
            reviewer_a_completed_at = plan_state.reviewer_a_completed_at
            reviewer_a_notes = str(plan_state.reviewer_a_notes or "").strip()
            reviewer_a_verdict = self._normalize_reviewer_a_verdict(plan_state.reviewer_a_verdict)
            reviewer_a_plan_signature = str(plan_state.reviewer_a_plan_signature or "").strip()
            reviewer_b_status = str(plan_state.reviewer_b_status or "not_started").strip().lower() or "not_started"
            reviewer_b_started_at = plan_state.reviewer_b_started_at
            reviewer_b_completed_at = plan_state.reviewer_b_completed_at
            reviewer_b_notes = str(plan_state.reviewer_b_notes or "").strip()
            reviewer_b_decision = self._normalize_reviewer_b_decision(plan_state.reviewer_b_decision)
            reviewer_b_plan_signature = str(plan_state.reviewer_b_plan_signature or "").strip()
            replan_required = bool(plan_state.replan_required)
            next_cycle_prompt = str(plan_state.next_cycle_prompt or "").strip()

            if plan_structure_changed:
                reviewer_a_status = "not_started"
                reviewer_a_started_at = None
                reviewer_a_completed_at = None
                reviewer_a_notes = ""
                reviewer_a_verdict = ""
                reviewer_a_plan_signature = ""
                reviewer_b_status = "not_started"
                reviewer_b_started_at = None
                reviewer_b_completed_at = None
                reviewer_b_notes = ""
                reviewer_b_decision = ""
                reviewer_b_plan_signature = ""
                replan_required = False
                next_cycle_prompt = ""
                closeout_status = "not_started"
                closeout_started_at = None
                closeout_completed_at = None
                closeout_commit_hash = None
                closeout_notes = ""
                self._clear_review_outputs(context)

            if reviewer_a_status in {"completed", "replan_required"} and reviewer_a_plan_signature != current_plan_signature:
                self._clear_review_outputs(context)
                reviewer_a_status = "not_started"
                reviewer_a_started_at = None
                reviewer_a_completed_at = None
                reviewer_a_notes = ""
                reviewer_a_verdict = ""
                reviewer_a_plan_signature = ""
                reviewer_b_status = "not_started"
                reviewer_b_started_at = None
                reviewer_b_completed_at = None
                reviewer_b_notes = ""
                reviewer_b_decision = ""
                reviewer_b_plan_signature = ""
                if not closeout_ready:
                    replan_required = False
                    next_cycle_prompt = ""

            if reviewer_b_status in {"completed", "replan_required"} and reviewer_b_plan_signature != current_plan_signature:
                self._clear_reviewer_b_outputs(context)
                reviewer_b_status = "not_started"
                reviewer_b_started_at = None
                reviewer_b_completed_at = None
                reviewer_b_notes = ""
                reviewer_b_decision = ""
                reviewer_b_plan_signature = ""
                replan_required = False
                next_cycle_prompt = ""
                closeout_status = "not_started"
                closeout_started_at = None
                closeout_completed_at = None
                closeout_commit_hash = None
                closeout_notes = ""

            if not closeout_ready:
                closeout_status = "not_started"
                closeout_started_at = None
                closeout_completed_at = None
                closeout_commit_hash = None
                closeout_notes = ""
                reviewer_b_status = "not_started"
                reviewer_b_started_at = None
                reviewer_b_completed_at = None
                reviewer_b_notes = ""
                reviewer_b_decision = ""
                reviewer_b_plan_signature = ""
                if reviewer_a_status != "replan_required":
                    replan_required = False
                    next_cycle_prompt = ""

            if reviewer_a_status not in {"running", "completed", "failed", "replan_required"}:
                reviewer_a_status = "not_started"
            if reviewer_a_status not in {"completed", "replan_required"}:
                reviewer_a_verdict = ""
                reviewer_a_plan_signature = ""
            if reviewer_a_status == "not_started":
                reviewer_a_started_at = None
                reviewer_a_completed_at = None
                reviewer_a_notes = ""

            if reviewer_b_status not in {"running", "completed", "failed", "replan_required"}:
                reviewer_b_status = "not_started"
            if reviewer_b_status not in {"completed", "replan_required"}:
                reviewer_b_decision = ""
                reviewer_b_plan_signature = ""
            if reviewer_b_status == "not_started":
                reviewer_b_started_at = None
                reviewer_b_completed_at = None
                reviewer_b_notes = ""

            state = ExecutionPlanState(
                plan_title=candidate_state.plan_title,
                project_prompt=candidate_state.project_prompt,
                summary=candidate_state.summary,
                workflow_mode=workflow_mode,
                execution_mode=execution_mode,
                default_test_command=candidate_state.default_test_command,
                last_updated_at="",
                reviewer_a_status=reviewer_a_status,
                reviewer_a_started_at=reviewer_a_started_at,
                reviewer_a_completed_at=reviewer_a_completed_at,
                reviewer_a_notes=reviewer_a_notes,
                reviewer_a_verdict=reviewer_a_verdict,
                reviewer_a_plan_signature=reviewer_a_plan_signature,
                reviewer_b_status=reviewer_b_status,
                reviewer_b_started_at=reviewer_b_started_at,
                reviewer_b_completed_at=reviewer_b_completed_at,
                reviewer_b_notes=reviewer_b_notes,
                reviewer_b_decision=reviewer_b_decision,
                reviewer_b_plan_signature=reviewer_b_plan_signature,
                replan_required=replan_required,
                next_cycle_prompt=next_cycle_prompt,
                closeout_status=closeout_status,
                closeout_title=plan_state.closeout_title.strip() or "Closeout",
                closeout_display_description=plan_state.closeout_display_description.strip() or "Closeout",
                closeout_codex_description=plan_state.closeout_codex_description.strip() or "Closeout",
                closeout_success_criteria=plan_state.closeout_success_criteria.strip() or "Closeout",
                closeout_deadline_at=plan_state.closeout_deadline_at.strip(),
                closeout_reasoning_effort=plan_state.closeout_reasoning_effort.strip() or "high",
                closeout_model_provider=plan_state.closeout_model_provider.strip().lower(),
                closeout_model=plan_state.closeout_model.strip().lower(),
                closeout_parallel_group=plan_state.closeout_parallel_group.strip(),
                closeout_depends_on=list(plan_state.closeout_depends_on),
                closeout_owned_paths=list(plan_state.closeout_owned_paths),
                closeout_started_at=closeout_started_at,
                closeout_completed_at=closeout_completed_at,
                closeout_commit_hash=closeout_commit_hash,
                closeout_notes=closeout_notes,
                steps=normalized_steps,
            )
            cached_state = prior_state
            if cached_state is not None and self._plan_state_content_signature(cached_state) == self._plan_state_content_signature(state):
                state.last_updated_at = cached_state.last_updated_at
            else:
                state.last_updated_at = now_utc_iso()
            write_json_if_changed(context.paths.execution_plan_file, state.to_dict())
            static_signature = self._static_plan_artifact_signature(context, state)
            if self._static_plan_artifacts_need_refresh(context, static_signature):
                self._save_execution_plan_static_artifacts(context, state)
                self._static_plan_artifact_signature_cache[self._execution_plan_cache_key(context)] = static_signature
            self._save_execution_plan_runtime_artifacts(context, state)
            self._cache_execution_plan_state(context, state)
            return state

    def _current_verify_state_fingerprint(self, context: ProjectContext, changed_files: list[str] | None = None) -> str:
        try:
            head_revision = self.git.current_revision(context.paths.repo_dir)
        except Exception:
            head_revision = ""
        return self.verification.build_state_fingerprint(
            context.paths.repo_dir,
            head_revision=head_revision,
            changed_paths=changed_files,
        )

    def _verification_output_guard_failure(
        self,
        test_result: TestRunResult,
    ) -> tuple[str, str, bool] | None:
        stdout = read_text(test_result.stdout_file)
        stderr = read_text(test_result.stderr_file)
        combined = "\n".join(
            part for part in (stdout, stderr, str(test_result.failure_reason or "").strip()) if part
        )
        if not combined.strip():
            return None
        for reason_code, pattern, message in self._VERIFICATION_INFRASTRUCTURE_PATTERNS:
            match = re.search(pattern, combined, re.IGNORECASE | re.MULTILINE)
            if match:
                detail = compact_text(match.group(0).strip(), max_chars=180)
                return reason_code, f"{message} {detail}".strip(), True
        for reason_code, pattern, message in self._VERIFICATION_FAILURE_PATTERNS:
            match = re.search(pattern, combined, re.IGNORECASE | re.MULTILINE)
            if match:
                detail = compact_text(match.group(0).strip(), max_chars=180)
                return reason_code, f"{message} {detail}".strip(), False
        return None

    def _step_scope_guard_failure(
        self,
        execution_step: ExecutionStep | None,
        changed_files: list[str] | None,
    ) -> tuple[str, str, bool] | None:
        normalized_changed_files = [
            path for path in self._normalize_owned_paths(changed_files or []) if not self._is_housekeeping_path(path)
        ]
        if not normalized_changed_files:
            if self._step_allows_read_only_completion(execution_step):
                return None
            return (
                "no_changed_files",
                "The block did not produce any repository changes, so it should not be treated as completed.",
                True,
            )
        if execution_step is None:
            return None
        owned_paths = self._normalize_owned_paths(getattr(execution_step, "owned_paths", []))
        if not owned_paths:
            return None
        for changed_path in normalized_changed_files:
            for owned_path in owned_paths:
                if self._owned_paths_overlap_level(changed_path, owned_path) != "none":
                    return None
        changed_preview = ", ".join(normalized_changed_files[:4])
        owned_preview = ", ".join(owned_paths[:4])
        return (
            "out_of_scope_changes",
            (
                "The block changed files outside the execution step scope. "
                f"Changed: {changed_preview or 'none'}. "
                f"Expected overlap with: {owned_preview or 'none'}."
            ),
            True,
        )

    def _is_housekeeping_path(self, path: str) -> bool:
        normalized = str(path or "").strip().replace("\\", "/").rstrip("/")
        if not normalized:
            return False
        if normalized in self._HOUSEKEEPING_PATHS:
            return True
        return any(normalized.startswith(f"{item}/") for item in self._HOUSEKEEPING_PATHS)

    def _step_allows_read_only_completion(self, execution_step: ExecutionStep | None) -> bool:
        if execution_step is None:
            return False
        step_kind = self._step_kind(execution_step)
        step_type = str(getattr(execution_step, "step_type", "") or "").strip().lower()
        if step_kind in {"barrier", "join"} or step_type in {"contract", "analysis", "review"}:
            return True
        metadata = execution_step.metadata if isinstance(execution_step.metadata, dict) else {}
        text_blob = " ".join(
            str(part or "").strip().lower()
            for part in (
                execution_step.title,
                execution_step.display_description,
                execution_step.codex_description,
                execution_step.success_criteria,
                metadata.get("implementation_notes", ""),
            )
        )
        read_only_markers = (
            "read-only",
            "do not modify",
            "without modifying",
            "no file writes",
            "inspect ",
            "confirm ",
            "validate ",
            "capture ",
            "check ",
        )
        return any(marker in text_blob for marker in read_only_markers)

    def _revert_housekeeping_changes(self, context: ProjectContext, execution_step: ExecutionStep | None) -> list[str]:
        changed_files = self.git.changed_files(context.paths.repo_dir)
        if not changed_files:
            return []
        if execution_step is not None:
            owned_paths = set(self._normalize_owned_paths(getattr(execution_step, "owned_paths", [])))
        else:
            owned_paths = set()
        revert_paths = [
            path
            for path in self._normalize_owned_paths(changed_files)
            if self._is_housekeeping_path(path) and path not in owned_paths
        ]
        if not revert_paths:
            return []
        self.git.run(["checkout", "--", *revert_paths], cwd=context.paths.repo_dir, check=False)
        return revert_paths

    def _apply_guard_failure(
        self,
        run_result: CodexRunResult,
        test_result: TestRunResult,
        *,
        reason_code: str,
        message: str,
    ) -> None:
        diagnostics = run_result.diagnostics if isinstance(run_result.diagnostics, dict) else {}
        diagnostics["guard_failure_reason_code"] = str(reason_code or "").strip()
        diagnostics["guard_failure_message"] = str(message or "").strip()
        run_result.diagnostics = diagnostics
        test_result.returncode = test_result.returncode or 1
        test_result.failure_reason = compact_text(str(message or "").strip(), max_chars=280)
        test_result.summary = compact_text(
            f"{test_result.summary} [guard:{reason_code}] {test_result.failure_reason}".strip(),
            max_chars=320,
        )

    def _guard_failure_from_run_result(self, run_result: CodexRunResult) -> tuple[str, str] | None:
        diagnostics = run_result.diagnostics if isinstance(run_result.diagnostics, dict) else {}
        reason_code = str(diagnostics.get("guard_failure_reason_code", "") or "").strip()
        if not reason_code:
            return None
        message = str(diagnostics.get("guard_failure_message", "") or "").strip() or "Execution guard rejected the block result."
        return reason_code, message

    def _debugger_skip_reason(
        self,
        *,
        changed_files: list[str] | None,
        test_result: TestRunResult,
        partial_failure: bool = False,
        guard_failure_reason: str | None = None,
    ) -> str | None:
        if partial_failure:
            return "partial_failure_prefers_serial_recovery"
        if str(guard_failure_reason or "").strip():
            return str(guard_failure_reason).strip()
        normalized_changed_files = [str(path).strip() for path in changed_files or [] if str(path).strip()]
        if not normalized_changed_files:
            return "no_changed_files"
        detail_text = " ".join(
            (
                str(test_result.summary or "").strip(),
                str(test_result.failure_reason or "").strip(),
                read_text(test_result.stderr_file),
            )
        ).lower()
        for marker in self._DEBUGGER_INFRASTRUCTURE_FAILURE_MARKERS:
            if marker in detail_text:
                return "verification_infrastructure_failure"
        return None

    def pending_execution_batches(self, plan_state: ExecutionPlanState) -> list[list[ExecutionStep]]:
        return execution_plan_support.pending_execution_batches(
            plan_state,
            normalized_execution_mode=self._normalize_execution_mode(plan_state.execution_mode),
            step_kind=self._step_kind,
        )

    def _normalize_execution_steps(
        self,
        context: ProjectContext,
        steps: list[ExecutionStep],
        default_test_command: str,
        execution_mode: str,
    ) -> list[ExecutionStep]:
        fallback_effort = normalize_reasoning_effort(context.runtime.effort, fallback="high")
        spine_version = current_spine_version(context.paths)
        raw_ids: list[str] = []
        seen_ids: set[str] = set()
        for index, step in enumerate(steps, start=1):
            candidate = step.step_id.strip() or f"TMP{index}"
            if candidate in seen_ids:
                candidate = f"TMP{index}"
            seen_ids.add(candidate)
            raw_ids.append(candidate)
        id_map = {raw_id: f"ST{index}" for index, raw_id in enumerate(raw_ids, start=1)}
        normalized_steps: list[ExecutionStep] = []
        for raw_id, step in zip(raw_ids, steps, strict=False):
            depends_on: list[str] = []
            owned_paths: list[str] = []
            metadata = deepcopy(step.metadata) if isinstance(step.metadata, dict) else {}
            if execution_mode == "parallel":
                for dependency in step.depends_on:
                    ref = dependency.strip()
                    if not ref:
                        continue
                    if ref not in id_map:
                        raise ValueError(f"Unknown dependency reference: {ref}")
                    if ref == raw_id:
                        raise ValueError(f"{raw_id} cannot depend on itself.")
                    depends_on.append(id_map[ref])
                seen_dependencies: set[str] = set()
                depends_on = [dep for dep in depends_on if not (dep in seen_dependencies or seen_dependencies.add(dep))]
                seen_paths: set[str] = set()
                for path in step.owned_paths:
                    normalized_path = self._normalize_owned_path(path)
                    if not normalized_path or normalized_path in seen_paths:
                        continue
                    seen_paths.add(normalized_path)
                    owned_paths.append(normalized_path)
                metadata = self._normalize_parallel_step_metadata(raw_id, metadata, id_map)
            normalized_model_provider = normalize_step_model_provider(step.model_provider)
            normalized_model = normalize_step_model(step.model)
            if normalized_model == "codex" and normalized_model_provider in {"openai", "ensemble"}:
                normalized_model = ""
            normalized_steps.append(
                normalize_execution_step_policy(
                    ExecutionStep(
                    step_id=id_map[raw_id],
                    title=step.title.strip(),
                    display_description=step.display_description.strip(),
                    codex_description=step.codex_description.strip() or step.display_description.strip() or step.title.strip(),
                    deadline_at=step.deadline_at.strip(),
                    model_provider=normalized_model_provider,
                    model=normalized_model,
                    test_command=step.test_command.strip() or default_test_command or context.runtime.test_cmd,
                    success_criteria=step.success_criteria.strip(),
                    step_type=step.step_type,
                    scope_class=step.scope_class,
                    spine_version=step.spine_version,
                    shared_contracts=list(step.shared_contracts),
                    verification_profile=step.verification_profile,
                    promotion_class=step.promotion_class,
                    primary_scope_paths=list(step.primary_scope_paths),
                    shared_reviewed_paths=list(step.shared_reviewed_paths),
                    forbidden_core_paths=list(step.forbidden_core_paths),
                    reasoning_effort=normalize_reasoning_effort(step.reasoning_effort, fallback=fallback_effort),
                    parallel_group=step.parallel_group.strip() if execution_mode == "parallel" else "",
                    depends_on=depends_on,
                    owned_paths=owned_paths,
                    status=step.status if step.status else "pending",
                    started_at=step.started_at,
                    completed_at=step.completed_at,
                    commit_hash=step.commit_hash,
                    notes=step.notes.strip(),
                    metadata=metadata,
                    ),
                    step_kind=self._step_kind(step),
                    current_spine_version=spine_version,
                )
            )
        if execution_mode == "parallel":
            self._reduce_redundant_parallel_dependencies(normalized_steps)
        self._normalize_hybrid_step_metadata(normalized_steps)
        if execution_mode == "parallel":
            self._validate_hybrid_execution_steps(normalized_steps)
        if execution_mode == "parallel" and self._plan_uses_dag_parallelism(normalized_steps):
            self._validate_parallel_execution_steps(normalized_steps)
        return normalized_steps

    def _normalize_parallel_step_metadata(
        self,
        raw_id: str,
        metadata: dict[str, object],
        id_map: dict[str, str],
    ) -> dict[str, object]:
        return execution_plan_support.normalize_parallel_step_metadata(raw_id, metadata, id_map)

    def _normalize_owned_path(self, value: str) -> str:
        return execution_plan_support.normalize_owned_path(value)

    def _reduce_redundant_parallel_dependencies(self, steps: list[ExecutionStep]) -> None:
        execution_plan_support.reduce_redundant_parallel_dependencies(steps, step_kind=self._step_kind)

    def _plan_uses_dag_parallelism(self, steps: list[ExecutionStep]) -> bool:
        return execution_plan_support.plan_uses_dag_parallelism(steps)

    def _validate_hybrid_execution_steps(self, steps: list[ExecutionStep]) -> None:
        step_ids = {step.step_id for step in steps}
        for step in steps:
            step_kind = self._step_kind(step)
            metadata = step.metadata if isinstance(step.metadata, dict) else {}
            step_label = self._step_trace_label(step)
            if step_kind in {"join", "barrier"} and step.parallel_group.strip():
                raise ValueError(f"{step_label} cannot use parallel_group because {step_kind} steps run alone.")
            if step_kind == "join":
                if len(step.depends_on) < 2:
                    raise ValueError(f"{step_label} must depend on at least two prior steps to act as a join node.")
                merge_from = self._coerce_string_list(metadata.get("merge_from", []))
                if len(merge_from) < 2:
                    raise ValueError(f"{step_label} must declare at least two merge_from step ids.")
                unknown_merge_targets = [item for item in merge_from if item not in step_ids]
                if unknown_merge_targets:
                    raise ValueError(f"{step_label} references unknown join targets: {', '.join(unknown_merge_targets)}")
                invalid_merge_targets = [item for item in merge_from if item not in step.depends_on]
                if invalid_merge_targets:
                    raise ValueError(
                        f"{step_label} can only merge direct dependencies, but merge_from included: {', '.join(invalid_merge_targets)}"
                    )
                join_policy = self._normalize_join_policy(metadata.get("join_policy", ""))
                if join_policy != "all":
                    raise ValueError(f"{step_label} uses unsupported join_policy '{join_policy}'. Only 'all' is supported.")
                metadata["join_policy"] = join_policy
                metadata["merge_from"] = merge_from
                step.metadata = metadata

    def _validate_parallel_execution_steps(self, steps: list[ExecutionStep]) -> None:
        execution_plan_support.validate_parallel_execution_steps(steps)

    def _owned_paths_overlap_level(self, left: str, right: str) -> str:
        return execution_plan_support.owned_paths_overlap_level(left, right)

    def _owned_paths_conflict(self, left: str, right: str) -> bool:
        return execution_plan_support.owned_paths_conflict(left, right)

    def _run_saved_execution_step_with_context(
        self,
        *,
        context: ProjectContext,
        runtime: RuntimeOptions,
        step_id: str | None = None,
        allow_push: bool = True,
        final_failure_reports: bool = True,
    ) -> tuple[ProjectContext, ExecutionPlanState, ExecutionStep]:
        plan_state = self.load_execution_plan_state(context)
        if not plan_state.steps:
            raise RuntimeError("No saved execution plan exists for this project.")
        ready_step_ids: set[str] | None = None
        if self._normalize_execution_mode(plan_state.execution_mode) == "parallel" and self._plan_uses_dag_parallelism(plan_state.steps):
            ready_step_ids = {item.step_id for batch in self.pending_execution_batches(plan_state) for item in batch}

        target_step: ExecutionStep | None = None
        for step in plan_state.steps:
            if step.status == "completed":
                continue
            if step_id and step.step_id != step_id:
                continue
            if ready_step_ids is not None and step.step_id not in ready_step_ids:
                if step_id:
                    raise RuntimeError(f"{step.step_id} is not dependency-ready yet.")
                continue
            target_step = step
            break
        if target_step is None:
            raise RuntimeError("No remaining execution step is available.")

        previous_runtime = context.runtime
        step_runtime = self._build_execution_step_runtime(
            previous_runtime,
            target_step,
            execution_mode=previous_runtime.execution_mode or "parallel",
            max_blocks=1,
            allow_push=allow_push,
            approval_mode=runtime.approval_mode,
            sandbox_mode=runtime.sandbox_mode,
            require_checkpoint_approval=False,
            checkpoint_interval_blocks=1,
        )
        preflight_error = self._execution_runtime_preflight_error(context, step_runtime)
        if preflight_error:
            failure = ExecutionPreflightError(preflight_error)
            for step in plan_state.steps:
                if step.step_id == target_step.step_id:
                    step.status = "failed"
                    step.completed_at = None
                    step.commit_hash = None
                    step.notes = str(failure)
                    self._set_step_failure_metadata(step, failure)
                elif step.status == "running":
                    step.status = "paused"
            context.loop_state.stop_reason = str(failure)
            context.metadata.current_status = "failed"
            context.metadata.last_run_at = now_utc_iso()
            plan_state.default_test_command = runtime.test_cmd
            plan_state = self.save_execution_plan_state(context, plan_state)
            self.workspace.save_project(context)
            target_step = next(step for step in plan_state.steps if step.step_id == target_step.step_id)
            return context, plan_state, target_step

        for step in plan_state.steps:
            if step.step_id == target_step.step_id:
                step.status = "running"
                step.started_at = step.started_at or now_utc_iso()
                step.notes = ""
                self._clear_step_failure_metadata(step)
            elif step.status == "running":
                step.status = "paused"
        context.metadata.current_status = f"running:{target_step.step_id.lower()}"
        context.metadata.last_run_at = now_utc_iso()
        plan_state.default_test_command = runtime.test_cmd
        plan_state = self.save_execution_plan_state(context, plan_state)

        context.runtime = step_runtime
        self.workspace.save_project(context)

        runner = CodexRunner(context.runtime.codex_path)
        memory = MemoryStore(context.paths)
        reporter = Reporter(context)
        candidate = CandidateTask(
            candidate_id=target_step.step_id,
            title=target_step.title,
            rationale=self._execution_step_rationale(target_step, context.runtime.test_cmd),
            plan_refs=[target_step.step_id],
            score=1.0,
        )
        target_step = next(step for step in plan_state.steps if step.step_id == target_step.step_id)
        try:
            latest_block, attempt_count = self._run_execution_step_attempts(
                context=context,
                runner=runner,
                memory=memory,
                reporter=reporter,
                candidate=candidate,
                execution_step=target_step,
                final_failure_reports=final_failure_reports,
            )
            if latest_block and latest_block.get("status") == "completed":
                target_step.status = "completed"
                target_step.completed_at = now_utc_iso()
                commit_hashes = latest_block.get("commit_hashes", [])
                if isinstance(commit_hashes, list) and commit_hashes:
                    target_step.commit_hash = str(commit_hashes[-1])
                target_step.notes = str(latest_block.get("test_summary", "")).strip()
                self._clear_step_failure_metadata(target_step)
                context.metadata.current_status = self._status_from_plan_state(plan_state)
            else:
                target_step.status = "failed"
                failure_summary = ""
                failure: ExecutionFailure | None = None
                if latest_block:
                    failure_summary = str(latest_block.get("test_summary", "")).strip()
                    failure = execution_failure_from_reason(
                        str(latest_block.get("failure_reason_code", "")).strip() or None,
                        failure_summary,
                    )
                if not failure_summary:
                    failure_summary = str(context.loop_state.stop_reason or f"Step execution failed after {attempt_count} attempt(s).").strip()
                failure = failure or ExecutionFailure(failure_summary or "Step execution failed.")
                target_step.notes = str(failure)
                self._set_step_failure_metadata(target_step, failure)
                context.metadata.current_status = "failed"
            self._collect_ml_step_report(context, target_step)
        except ImmediateStopRequested as exc:
            self.git.hard_reset(context.paths.repo_dir, context.metadata.current_safe_revision or self.git.current_revision(context.paths.repo_dir))
            target_step.status = "paused"
            target_step.completed_at = None
            target_step.commit_hash = None
            target_step.notes = str(exc).strip() or "Immediate stop requested."
            self._clear_step_failure_metadata(target_step)
            context.metadata.current_status = self._status_from_plan_state(plan_state)
        except HANDLED_OPERATION_EXCEPTIONS as exc:
            failure = exc if isinstance(exc, ExecutionFailure) else ExecutionFailure(str(exc).strip() or "Step execution failed.")
            target_step.status = "failed"
            target_step.notes = str(failure)
            self._set_step_failure_metadata(target_step, failure)
            self._collect_ml_step_report(context, target_step)
            context.metadata.current_status = "failed"
            if failure is exc:
                raise
            raise failure from exc
        finally:
            context.runtime = previous_runtime
            self.save_execution_plan_state(context, plan_state)
            self.workspace.save_project(context)

        return context, plan_state, target_step

    def run_saved_execution_step(
        self,
        project_dir: Path,
        runtime: RuntimeOptions,
        step_id: str | None = None,
        branch: str = "main",
        origin_url: str = "",
    ) -> tuple[ProjectContext, ExecutionPlanState, ExecutionStep]:
        context, _plan_state = self._require_pre_execution_review_ready(
            project_dir=project_dir,
            runtime=runtime,
            branch=branch,
            origin_url=origin_url,
        )
        return self._run_saved_execution_step_with_context(context=context, runtime=runtime, step_id=step_id)

    def _run_execution_step_attempts(
        self,
        *,
        context: ProjectContext,
        runner: CodexRunner,
        memory: MemoryStore,
        reporter: Reporter,
        candidate: CandidateTask,
        execution_step: ExecutionStep,
        final_failure_reports: bool = True,
    ) -> tuple[dict[str, object] | None, int]:
        attempt_limit = max(1, int(context.runtime.regression_limit or 1))
        lineage_id = self._execution_step_lineage_id(execution_step)
        latest_block: dict[str, object] | None = None
        attempts = 0
        while attempts < attempt_limit:
            attempts += 1
            previous_block = self._latest_logged_block_for_lineage(context.paths.block_log_file, lineage_id)
            previous_block_index = int(previous_block.get("block_index", -1)) if previous_block else -1
            self._run_single_block(
                context=context,
                runner=runner,
                memory=memory,
                reporter=reporter,
                candidate_override=candidate,
                execution_step_override=execution_step,
                suppress_failure_reporting=not final_failure_reports or attempts < attempt_limit,
            )
            context.metadata.last_run_at = now_utc_iso()
            latest_block = self._latest_logged_block_for_lineage(context.paths.block_log_file, lineage_id)
            latest_block_index = int(latest_block.get("block_index", -1)) if latest_block else -1
            if latest_block_index <= previous_block_index:
                latest_block = None
            if latest_block and latest_block.get("status") == "completed":
                return latest_block, attempts
            if context.loop_state.stop_reason:
                break
            if attempts < attempt_limit:
                context.metadata.current_status = f"running:retry-{execution_step.step_id.lower()}"
        return latest_block, attempts

    def run_parallel_execution_batch(
        self,
        project_dir: Path,
        runtime: RuntimeOptions,
        step_ids: list[str],
        branch: str = "main",
        origin_url: str = "",
    ) -> tuple[ProjectContext, ExecutionPlanState, list[ExecutionStep]]:
        context, _plan_state = self._require_pre_execution_review_ready(
            project_dir=project_dir,
            runtime=runtime,
            branch=branch,
            origin_url=origin_url,
        )
        return self._run_parallel_execution_batch_with_context(
            context=context,
            runtime=runtime,
            step_ids=step_ids,
        )

    def _run_parallel_execution_batch_with_context(
        self,
        *,
        context: ProjectContext,
        runtime: RuntimeOptions,
        step_ids: list[str],
    ) -> tuple[ProjectContext, ExecutionPlanState, list[ExecutionStep]]:
        project_dir = context.paths.repo_dir
        branch = context.metadata.branch or "main"
        origin_url = context.metadata.origin_url or ""
        plan_state = self.load_execution_plan_state(context)
        if not plan_state.steps:
            raise RuntimeError("No saved execution plan exists for this project.")
        if not [step_id.strip() for step_id in step_ids if step_id.strip()]:
            raise RuntimeError("No execution step ids were provided.")
        hybrid_lineages = self._plan_uses_hybrid_lineages(plan_state)
        if not hybrid_lineages and len(step_ids) < 2:
            raise ValueError("Parallel execution batch requires at least two step ids.")

        ordered_targets: list[ExecutionStep] = []
        requested = {step_id.strip() for step_id in step_ids if step_id.strip()}
        for step in plan_state.steps:
            if step.step_id in requested:
                if step.status == "completed":
                    raise RuntimeError(f"{step.step_id} is already completed.")
                ordered_targets.append(step)
        if not ordered_targets:
            raise RuntimeError("No remaining parallel batch steps were found.")
        allowed_batches = [
            [item.step_id for item in batch]
            for batch in self.pending_execution_batches(plan_state)
            if hybrid_lineages or len(batch) > 1
        ]
        requested_signature = [step.step_id for step in ordered_targets]
        if requested_signature not in allowed_batches:
            raise RuntimeError("Requested parallel batch is not currently ready in the execution DAG.")
        if hybrid_lineages:
            if any(self._step_kind(step) in {"join", "barrier"} for step in ordered_targets):
                if len(ordered_targets) != 1:
                    raise RuntimeError("Join and barrier steps must run as singleton batches.")
                project, saved, result_step = self.run_join_execution_step(
                    project_dir=project_dir,
                    runtime=runtime,
                    step_id=ordered_targets[0].step_id,
                    branch=branch,
                    origin_url=origin_url,
                )
                return project, saved, [result_step]
            lineages = self._load_lineage_states(context)
            if not self._batch_uses_hybrid_lineages(plan_state, ordered_targets, lineages=lineages):
                project, saved, result_step = self._run_saved_execution_step_with_context(
                    context=context,
                    runtime=runtime,
                    step_id=ordered_targets[0].step_id,
                )
                return project, saved, [result_step]
            return self._run_lineage_execution_batch(context, plan_state, runtime, ordered_targets)
        if len(ordered_targets) < 2:
            raise ValueError("Parallel execution batch requires at least two ready task steps.")

        batch_label = ", ".join(step.step_id for step in ordered_targets)
        batch_started_at = now_utc_iso()
        for step in plan_state.steps:
            if step.step_id in requested:
                step.status = "running"
                step.started_at = step.started_at or batch_started_at
                step.notes = ""
            elif step.status == "running":
                step.status = "paused"
        plan_state.default_test_command = runtime.test_cmd
        plan_state.execution_mode = "parallel"
        plan_state = self.save_execution_plan_state(context, plan_state)
        # save_execution_plan_state normalizes and recreates step objects, so refresh
        # the batch targets before mutating status/notes during execution.
        refreshed_targets = {step.step_id: step for step in plan_state.steps}
        ordered_targets = [refreshed_targets[step.step_id] for step in ordered_targets]

        previous_runtime = context.runtime
        context.runtime = RuntimeOptions(
            **{
                **previous_runtime.to_dict(),
                "execution_mode": "parallel",
                "parallel_worker_mode": normalize_parallel_worker_mode(getattr(runtime, "parallel_worker_mode", "auto")),
                "parallel_workers": max(0, int(getattr(runtime, "parallel_workers", 0) or 0)),
                "allow_push": True,
                "approval_mode": runtime.approval_mode,
                "sandbox_mode": runtime.sandbox_mode,
                "require_checkpoint_approval": False,
                "checkpoint_interval_blocks": 1,
            }
        )
        context.metadata.current_status = "running:parallel"
        context.metadata.last_run_at = batch_started_at
        resolved_worker_count = self._parallel_worker_count(context.runtime)
        context.loop_state.current_task = f"Parallel batch {batch_label} (workers {resolved_worker_count})"
        self.save_execution_plan_state(context, plan_state)
        self.workspace.save_project(context)

        reporter = Reporter(context)
        base_revision = context.metadata.current_safe_revision or self.git.current_revision(context.paths.repo_dir)
        batch_token = self._parallel_batch_token()
        worker_results: list[dict[str, object]] = []
        merged_commit_hashes: list[str] = []
        merged_commit_by_step_id: dict[str, str] = {}
        group_test_result: TestRunResult | None = None
        rollback_status = "not_needed"
        final_status = "completed"
        batch_summary = ""
        failure_extra: dict[str, object] | None = None

        try:
            worker_limit = min(len(ordered_targets), self._parallel_worker_count(context.runtime))
            with ThreadPoolExecutor(max_workers=worker_limit) as executor:
                future_map = {
                    executor.submit(
                        self._run_parallel_step_worker,
                        context,
                        runtime,
                        step,
                        base_revision,
                        batch_token,
                        index,
                    ): step.step_id
                    for index, step in enumerate(ordered_targets, start=1)
                }
                by_step_id: dict[str, dict[str, object]] = {}
                for future in as_completed(future_map):
                    result = future.result()
                    result_step_id = str(result["step_id"])
                    by_step_id[result_step_id] = result
                    plan_state, ordered_targets = self._sync_parallel_batch_step_progress(
                        context=context,
                        plan_state=plan_state,
                        ordered_targets=ordered_targets,
                        step_id=result_step_id,
                        worker_result=result,
                        success_status="integrating",
                        running_status="running:parallel",
                        failure_status="pending",
                        failure_project_status="running:parallel",
                    )
                worker_results = [by_step_id[step.step_id] for step in ordered_targets]

            paused_worker = next((item for item in worker_results if self._parallel_worker_status(item) == "paused"), None)
            failed_worker = next((item for item in worker_results if self._parallel_worker_status(item) == "failed"), None)
            completed_step_ids = {
                str(item.get("step_id") or "").strip()
                for item in worker_results
                if self._parallel_worker_status(item) == "completed"
            }
            successful_targets = [step for step in ordered_targets if step.step_id in completed_step_ids]
            partial_failure = failed_worker is not None and bool(successful_targets)
            if paused_worker is not None:
                final_status = "paused"
                rollback_status = "rolled_back_to_safe_revision"
                batch_summary = str(paused_worker.get("notes") or "Immediate stop requested.").strip()
                self.git.abort_cherry_pick(context.paths.repo_dir)
                self.git.hard_reset(context.paths.repo_dir, base_revision)
                for step in ordered_targets:
                    step.status = "paused"
                    step.completed_at = None
                    step.commit_hash = None
                    step.notes = batch_summary
                context.metadata.current_status = self._status_from_plan_state(plan_state)
            elif failed_worker is not None and not successful_targets:
                rollback_status = "serial_recovery_after_worker_failure"
                initial_summary, failure_extra = self._parallel_partial_failure_details(ordered_targets, worker_results)
                recovery_ids = [step.step_id for step in ordered_targets]
                plan_state, ordered_targets, recovery_status, recovery_summary = self._run_parallel_serial_recovery(
                    context=context,
                    runtime=runtime,
                    ordered_targets=ordered_targets,
                    recovery_step_ids=recovery_ids,
                )
                batch_summary = f"{initial_summary} | {recovery_summary}".strip(" |")
                if recovery_status == "paused":
                    final_status = "paused"
                    rollback_status = "rolled_back_to_safe_revision"
                elif recovery_status == "deferred":
                    final_status = "deferred"
                    rollback_status = "parallel_recovery_deferred"
                else:
                    final_status = "completed"
            else:
                verification_block_index = max(1, context.loop_state.block_index + len(ordered_targets))
                batch_targets = successful_targets or ordered_targets
                batch_merge_step = self._build_parallel_batch_merge_step(
                    batch_targets,
                    plan_state.default_test_command or runtime.test_cmd,
                )
                batch_merge_candidate = CandidateTask(
                    candidate_id="parallel-batch-merge",
                    title=batch_merge_step.title,
                    rationale=self._execution_step_rationale(batch_merge_step, batch_merge_step.test_command),
                    plan_refs=[step.step_id for step in batch_targets],
                    score=1.0,
                )
                batch_debug_step = self._build_parallel_batch_debug_step(
                    batch_targets,
                    plan_state.default_test_command or runtime.test_cmd,
                )
                batch_candidate = CandidateTask(
                    candidate_id="parallel-batch-debug",
                    title=batch_debug_step.title,
                    rationale=self._execution_step_rationale(batch_debug_step, batch_debug_step.test_command),
                    plan_refs=[step.step_id for step in batch_targets],
                    score=1.0,
                )
                batch_memory_context = MemoryStore(context.paths).render_context(read_text(context.paths.mid_term_plan_file))
                batch_runner = CodexRunner(context.runtime.codex_path)
                try:
                    for result in worker_results:
                        result_step_id = str(result.get("step_id") or "").strip()
                        if result_step_id not in completed_step_ids:
                            continue
                        worker_commit = str(result.get("commit_hash") or "").strip()
                        if not worker_commit:
                            merged_commit_by_step_id[result_step_id] = ""
                            continue
                        merged_commit, _used_merger = self._apply_cherry_pick_with_merger(
                            context=context,
                            source_commit=worker_commit,
                            runner=batch_runner,
                            reporter=reporter,
                            block_index=verification_block_index,
                            candidate=batch_merge_candidate,
                            execution_step=batch_merge_step,
                            memory_context=batch_memory_context,
                            merge_targets=[step.step_id for step in batch_targets],
                            failing_command="parallel-batch-merge",
                            conflict_test_result_factory=lambda merge_result, conflicted_files, worker_commit=worker_commit: self._parallel_merge_conflict_test_result(
                                context=context,
                                worker_commit=worker_commit,
                                merge_result=merge_result,
                                conflicted_files=conflicted_files,
                            ),
                            conflict_message_factory=lambda conflicted_files, merge_result, worker_commit=worker_commit: (
                                f"Parallel merge conflict while cherry-picking {worker_commit}: "
                                f"{', '.join(conflicted_files) or str(getattr(merge_result, 'stderr', '')).strip() or 'unknown conflict'}"
                            ),
                            post_success_strategy="continue_cherry_pick",
                        )
                        merged_commit_hashes.append(merged_commit)
                        merged_commit_by_step_id[result_step_id] = merged_commit
                except ImmediateStopRequested as exc:
                    self.git.abort_cherry_pick(context.paths.repo_dir)
                    self.git.hard_reset(context.paths.repo_dir, base_revision)
                    rollback_status = "rolled_back_to_safe_revision"
                    final_status = "paused"
                    batch_summary = str(exc).strip() or "Immediate stop requested."
                    for step in ordered_targets:
                        step.status = "paused"
                        step.completed_at = None
                        step.commit_hash = None
                        step.notes = batch_summary
                    context.metadata.current_status = self._status_from_plan_state(plan_state)
                except HANDLED_OPERATION_EXCEPTIONS as exc:
                    self.git.abort_cherry_pick(context.paths.repo_dir)
                    self.git.hard_reset(context.paths.repo_dir, base_revision)
                    rollback_status = "serial_recovery_after_merge_failure"
                    merge_summary = str(exc).strip() or "Parallel merge failed."
                    recovery_ids = [step.step_id for step in ordered_targets]
                    plan_state, ordered_targets, recovery_status, recovery_summary = self._run_parallel_serial_recovery(
                        context=context,
                        runtime=runtime,
                        ordered_targets=ordered_targets,
                        recovery_step_ids=recovery_ids,
                    )
                    batch_summary = f"{merge_summary} | {recovery_summary}".strip(" |")
                    if recovery_status == "paused":
                        final_status = "paused"
                        rollback_status = "rolled_back_to_safe_revision"
                    elif recovery_status == "deferred":
                        final_status = "deferred"
                        rollback_status = "parallel_recovery_deferred"
                    else:
                        final_status = "completed"
                else:
                    try:
                        batch_changed_files = sorted(
                            {
                                str(path).strip()
                                for result in worker_results
                                for path in (result.get("changed_files") or [])
                                if str(path).strip()
                            }
                        )
                        if any(commit_hash.strip() for commit_hash in merged_commit_hashes):
                            close_block_index = max(1, context.loop_state.block_index + len(ordered_targets))
                            group_test_result = self._run_test_command(
                                context,
                                close_block_index,
                                "parallel-batch-pass",
                                state_fingerprint=self._current_verify_state_fingerprint(context, batch_changed_files),
                            )
                            reporter.save_test_result(close_block_index, "parallel-batch-pass", group_test_result)
                        else:
                            group_test_result = self._run_test_command(
                                context,
                                verification_block_index,
                                "parallel-batch-pass",
                                state_fingerprint=self._current_verify_state_fingerprint(context, batch_changed_files),
                            )
                            reporter.save_test_result(verification_block_index, "parallel-batch-pass", group_test_result)
                        if group_test_result and group_test_result.returncode != 0:
                            debugger_skip_reason = self._debugger_skip_reason(
                                changed_files=batch_changed_files,
                                test_result=group_test_result,
                                partial_failure=partial_failure,
                            )
                            if debugger_skip_reason:
                                self.git.hard_reset(context.paths.repo_dir, base_revision)
                                rollback_status = "serial_recovery_after_batch_verification"
                                batch_summary = (
                                    "Parallel batch verification failed and debugger recovery was skipped: "
                                    f"{debugger_skip_reason}."
                                )
                                group_test_result = None
                                recovery_ids = [step.step_id for step in ordered_targets]
                                plan_state, ordered_targets, recovery_status, recovery_summary = self._run_parallel_serial_recovery(
                                    context=context,
                                    runtime=runtime,
                                    ordered_targets=ordered_targets,
                                    recovery_step_ids=recovery_ids,
                                )
                                batch_summary = f"{batch_summary} | {recovery_summary}".strip(" |")
                                if recovery_status == "paused":
                                    final_status = "paused"
                                    rollback_status = "rolled_back_to_safe_revision"
                                elif recovery_status == "deferred":
                                    final_status = "deferred"
                                    rollback_status = "parallel_recovery_deferred"
                                else:
                                    final_status = "completed"
                            else:
                                debug_pass_name, debug_run_result, debug_test_result, debug_commit_hash = self._run_debugger_pass(
                                    context=context,
                                    runner=batch_runner,
                                    reporter=reporter,
                                    block_index=verification_block_index,
                                    candidate=batch_candidate,
                                    execution_step=batch_debug_step,
                                    memory_context=batch_memory_context,
                                    failing_pass_name="parallel-batch-pass",
                                    failing_test_result=group_test_result,
                                )
                                if debug_run_result.returncode != 0 or debug_test_result is None or debug_test_result.returncode != 0:
                                    self.git.hard_reset(context.paths.repo_dir, base_revision)
                                    rollback_status = "serial_recovery_after_batch_debugger"
                                    batch_summary = "Parallel batch verification failed and debugger recovery did not fix it."
                                    group_test_result = None
                                    self._log_pass_result(
                                        context=context,
                                        reporter=reporter,
                                        block_index=verification_block_index,
                                        candidate=batch_candidate,
                                        pass_name=debug_pass_name,
                                        run_result=debug_run_result,
                                        test_result=debug_test_result,
                                        commit_hash=None,
                                        rollback_status=rollback_status,
                                        search_enabled=False,
                                    )
                                    recovery_ids = [step.step_id for step in ordered_targets]
                                    plan_state, ordered_targets, recovery_status, recovery_summary = self._run_parallel_serial_recovery(
                                        context=context,
                                        runtime=runtime,
                                        ordered_targets=ordered_targets,
                                        recovery_step_ids=recovery_ids,
                                    )
                                    batch_summary = f"{batch_summary} | {recovery_summary}".strip(" |")
                                    if recovery_status == "paused":
                                        final_status = "paused"
                                        rollback_status = "rolled_back_to_safe_revision"
                                    elif recovery_status == "deferred":
                                        final_status = "deferred"
                                        rollback_status = "parallel_recovery_deferred"
                                    else:
                                        final_status = "completed"
                                else:
                                    self._log_pass_result(
                                        context=context,
                                        reporter=reporter,
                                        block_index=verification_block_index,
                                        candidate=batch_candidate,
                                        pass_name=debug_pass_name,
                                        run_result=debug_run_result,
                                        test_result=debug_test_result,
                                        commit_hash=debug_commit_hash,
                                        rollback_status="not_needed",
                                        search_enabled=False,
                                    )
                                    if debug_commit_hash:
                                        merged_commit_hashes.append(debug_commit_hash)
                                    group_test_result = debug_test_result
                                    batch_summary = debug_test_result.summary
                                    if partial_failure:
                                        partial_summary, partial_extra = self._parallel_partial_failure_details(ordered_targets, worker_results)
                                        rollback_status = "serial_recovery_after_worker_failure"
                                        recovery_ids = [step.step_id for step in ordered_targets if step.step_id not in completed_step_ids]
                                        failure_extra = {
                                            **(failure_extra or {}),
                                            **partial_extra,
                                        }
                                    merged_commits = [item for item in merged_commit_hashes if item]
                                    if merged_commits:
                                        last_commit = merged_commits[-1]
                                        context.metadata.current_safe_revision = last_commit
                                        context.loop_state.current_safe_revision = last_commit
                                        context.loop_state.last_commit_hash = last_commit
                                    self._apply_parallel_batch_outcomes(
                                        ordered_targets,
                                        worker_results,
                                        completed_step_ids=completed_step_ids,
                                        merged_commit_by_step_id=merged_commit_by_step_id,
                                        completed_note=debug_test_result.summary,
                                    )
                                    plan_state = self.save_execution_plan_state(context, plan_state)
                                    ordered_targets = self._refresh_ordered_targets(plan_state, ordered_targets)
                                    context.metadata.current_status = self._status_from_plan_state(plan_state)
                                    if partial_failure:
                                        plan_state, ordered_targets, recovery_status, recovery_summary = self._run_parallel_serial_recovery(
                                            context=context,
                                            runtime=runtime,
                                            ordered_targets=ordered_targets,
                                            recovery_step_ids=recovery_ids,
                                        )
                                        batch_summary = f"{partial_summary} | {debug_test_result.summary} | {recovery_summary}".strip(" |")
                                        if recovery_status == "paused":
                                            final_status = "paused"
                                            rollback_status = "rolled_back_to_safe_revision"
                                        elif recovery_status == "deferred":
                                            final_status = "deferred"
                                            rollback_status = "parallel_recovery_deferred"
                                        else:
                                            final_status = "completed"
                                    else:
                                        batch_summary = debug_test_result.summary
                        else:
                            batch_summary = group_test_result.summary if group_test_result else "Parallel batch completed successfully."
                            if partial_failure:
                                partial_summary, partial_extra = self._parallel_partial_failure_details(ordered_targets, worker_results)
                                rollback_status = "serial_recovery_after_worker_failure"
                                recovery_ids = [step.step_id for step in ordered_targets if step.step_id not in completed_step_ids]
                                failure_extra = {
                                    **(failure_extra or {}),
                                    **partial_extra,
                                }
                            self._apply_parallel_batch_outcomes(
                                ordered_targets,
                                worker_results,
                                completed_step_ids=completed_step_ids,
                                merged_commit_by_step_id=merged_commit_by_step_id,
                                completed_note=batch_summary,
                            )
                            plan_state = self.save_execution_plan_state(context, plan_state)
                            ordered_targets = self._refresh_ordered_targets(plan_state, ordered_targets)
                            merged_commits = [item for item in merged_commit_hashes if item]
                            if merged_commits:
                                last_commit = merged_commits[-1]
                                context.metadata.current_safe_revision = last_commit
                                context.loop_state.current_safe_revision = last_commit
                                context.loop_state.last_commit_hash = last_commit
                                pushed, push_reason = self._push_if_ready(
                                    context,
                                    context.paths.repo_dir,
                                    context.metadata.branch,
                                    commit_hash=last_commit,
                                )
                                if not pushed and push_reason not in {"already_up_to_date"}:
                                    batch_summary = (batch_summary + f" | push skipped: {push_reason}").strip(" |")
                            context.metadata.current_status = self._status_from_plan_state(plan_state)
                            if partial_failure:
                                plan_state, ordered_targets, recovery_status, recovery_summary = self._run_parallel_serial_recovery(
                                    context=context,
                                    runtime=runtime,
                                    ordered_targets=ordered_targets,
                                    recovery_step_ids=recovery_ids,
                                )
                                batch_summary = f"{partial_summary} | {batch_summary} | {recovery_summary}".strip(" |")
                                if recovery_status == "paused":
                                    final_status = "paused"
                                    rollback_status = "rolled_back_to_safe_revision"
                                elif recovery_status == "deferred":
                                    final_status = "deferred"
                                    rollback_status = "parallel_recovery_deferred"
                                else:
                                    final_status = "completed"
                    except ImmediateStopRequested as exc:
                        self.git.abort_cherry_pick(context.paths.repo_dir)
                        self.git.hard_reset(context.paths.repo_dir, base_revision)
                        rollback_status = "rolled_back_to_safe_revision"
                        final_status = "paused"
                        batch_summary = str(exc).strip() or "Immediate stop requested."
                        group_test_result = None
                        for step in ordered_targets:
                            step.status = "paused"
                            step.completed_at = None
                            step.commit_hash = None
                            step.notes = batch_summary
                        context.metadata.current_status = self._status_from_plan_state(plan_state)

            next_block_index = context.loop_state.block_index
            combined_changed_files: list[str] = []
            for index, step in enumerate(ordered_targets):
                next_block_index += 1
                worker_result = worker_results[index] if index < len(worker_results) else {}
                pass_entry = deepcopy(worker_result.get("pass_log") or {})
                block_entry = deepcopy(worker_result.get("block_log") or {})
                changed_files = sorted(set(str(item) for item in worker_result.get("changed_files", []) if str(item).strip()))
                combined_changed_files.extend(changed_files)
                lineage_id = str(worker_result.get("lineage_id") or self._execution_step_lineage_id(step)).strip()
                pass_entry.update(
                    {
                        "repository_id": context.metadata.repo_id,
                        "repository_slug": context.metadata.slug,
                        "block_index": next_block_index,
                        "lineage_id": lineage_id or None,
                        "selected_task": step.title,
                        "commit_hash": step.commit_hash if step.status == "completed" else None,
                        "rollback_status": (
                            "not_needed"
                            if step.status == "completed"
                            else ("parallel_recovery_deferred" if step.status == "pending" else rollback_status)
                        ),
                        "changed_files": changed_files,
                        "test_results": group_test_result.to_dict() if group_test_result and step.status == "completed" else None,
                    }
                )
                block_entry.update(
                    {
                        "repository_id": context.metadata.repo_id,
                        "repository_slug": context.metadata.slug,
                        "block_index": next_block_index,
                        "lineage_id": lineage_id or None,
                        "status": self._parallel_batch_log_status(step.status),
                        "selected_task": step.title,
                        "changed_files": changed_files,
                        "test_summary": step.notes or batch_summary,
                        "commit_hashes": [step.commit_hash] if step.commit_hash else [],
                        "rollback_status": (
                            "not_needed"
                            if step.status == "completed"
                            else ("parallel_recovery_deferred" if step.status == "pending" else rollback_status)
                        ),
                    }
                )
                reporter.log_pass(pass_entry)
                reporter.log_block(block_entry)
                reporter.append_attempt_history(
                    attempt_history_entry(
                        next_block_index,
                        step.title,
                        self._parallel_batch_attempt_status(step.status),
                        [step.commit_hash] if step.commit_hash else [],
                    )
                )
                self._collect_ml_step_report(
                    context,
                    step,
                    report_payload=worker_result.get("ml_report_payload") if isinstance(worker_result.get("ml_report_payload"), dict) else {},
                )
            context.loop_state.block_index = next_block_index
            context.loop_state.last_block_completed_at = now_utc_iso()
            reporter.write_block_review(
                reflection_markdown(
                    f"Parallel batch {batch_label}",
                    batch_summary or "Parallel batch finished.",
                    sorted(set(combined_changed_files)),
                    [item for item in merged_commit_hashes if item],
                )
            )
            if final_status == "failed":
                self._report_failure(
                    context,
                    reporter,
                    failure_type="parallel_batch_failed",
                    summary=batch_summary or "Parallel batch failed.",
                    block_index=context.loop_state.block_index,
                    selected_task=f"Parallel batch {batch_label}",
                    extra=failure_extra,
                )
            return context, self.save_execution_plan_state(context, plan_state), ordered_targets
        finally:
            context.runtime = previous_runtime
            context.metadata.last_run_at = now_utc_iso()
            self.workspace.save_project(context)
            for result in worker_results:
                self._cleanup_parallel_worker(context.paths.repo_dir, result)

    def run_join_execution_step(
        self,
        project_dir: Path,
        runtime: RuntimeOptions,
        step_id: str,
        branch: str = "main",
        origin_url: str = "",
    ) -> tuple[ProjectContext, ExecutionPlanState, ExecutionStep]:
        context, _plan_state = self._require_pre_execution_review_ready(
            project_dir=project_dir,
            runtime=runtime,
            branch=branch,
            origin_url=origin_url,
        )
        plan_state = self.load_execution_plan_state(context)
        if not plan_state.steps:
            raise RuntimeError("No saved execution plan exists for this project.")

        ready_step_ids = {item.step_id for batch in self.pending_execution_batches(plan_state) for item in batch}
        target_step = next(
            (
                step
                for step in plan_state.steps
                if step.step_id == step_id.strip()
                and step.status != "completed"
                and step.step_id in ready_step_ids
            ),
            None,
        )
        if target_step is None:
            raise RuntimeError(f"{step_id} is not dependency-ready yet.")
        if self._step_kind(target_step) not in {"join", "barrier"}:
            raise RuntimeError(f"{target_step.step_id} is not a join or barrier step.")

        started_at = now_utc_iso()
        for step in plan_state.steps:
            if step.step_id == target_step.step_id:
                step.status = "running"
                step.started_at = step.started_at or started_at
                step.notes = ""
                self._clear_step_failure_metadata(step)
            elif step.status == "running":
                step.status = "paused"
        plan_state.default_test_command = runtime.test_cmd
        plan_state = self.save_execution_plan_state(context, plan_state)
        target_step = next(step for step in plan_state.steps if step.step_id == target_step.step_id)

        lineages = self._load_lineage_states(context)
        merge_targets = self._merge_targets_for_lineages(plan_state, target_step)
        merge_lineages = self._lineages_for_join_step(plan_state, target_step, lineages)
        pre_join_safe_revision = context.metadata.current_safe_revision or self.git.current_revision(context.paths.repo_dir)
        context.metadata.current_safe_revision = pre_join_safe_revision
        context.loop_state.current_safe_revision = pre_join_safe_revision
        context.metadata.current_status = f"running:{target_step.step_id.lower()}"
        context.metadata.last_run_at = started_at
        self.workspace.save_project(context)
        attempt_limit = max(1, int(runtime.regression_limit or 1))
        last_failure_note = ""
        last_failure_exc: ExecutionFailure | None = None

        for attempt_index in range(1, attempt_limit + 1):
            integration_info: dict[str, object] | None = None
            integration_context: ProjectContext | None = None
            try:
                integration_token = self._integration_token(target_step)
                integration_info = self._build_integration_context(
                    context,
                    runtime,
                    target_step,
                    pre_join_safe_revision,
                    integration_token,
                )
                integration_context = integration_info.get("integration_context")
                if not isinstance(integration_context, ProjectContext):
                    raise RuntimeError("Integration context could not be created.")
                integration_plan_state = self.save_execution_plan_state(integration_context, deepcopy(plan_state))
                self._save_lineage_states(integration_context, lineages)
                integration_manifests = []
                for lineage in merge_lineages:
                    integration_manifests.extend(load_lineage_manifests(context.paths, lineage_id=lineage.lineage_id))
                if integration_manifests:
                    write_text(integration_context.paths.block_review_file, manifest_summary_markdown(integration_manifests))
                integration_runner = CodexRunner(integration_context.runtime.codex_path)
                integration_reporter = Reporter(integration_context)
                integration_memory_context = MemoryStore(integration_context.paths).render_context(read_text(integration_context.paths.mid_term_plan_file))
                merge_step = self._build_join_merge_step(integration_plan_state, target_step, merge_targets)
                merge_candidate = CandidateTask(
                    candidate_id=f"{target_step.step_id}-merge",
                    title=merge_step.title,
                    rationale=self._execution_step_rationale(merge_step, merge_step.test_command),
                    plan_refs=merge_targets,
                    score=1.0,
                )
                merge_block_index = self._next_logged_block_index(integration_context)

                for lineage in merge_lineages:
                    source_commit = str(lineage.head_commit or lineage.safe_revision or "").strip()
                    if not source_commit:
                        raise RuntimeError(f"{target_step.step_id} could not find a mergeable commit for lineage {lineage.lineage_id}.")
                    _merged_revision, used_merger = self._apply_cherry_pick_with_merger(
                        context=integration_context,
                        source_commit=source_commit,
                        runner=integration_runner,
                        reporter=integration_reporter,
                        block_index=merge_block_index,
                        candidate=merge_candidate,
                        execution_step=merge_step,
                        memory_context=integration_memory_context,
                        merge_targets=merge_targets,
                        failing_command="integration-merge",
                        conflict_test_result_factory=lambda merge_result, conflicted_files, source_commit=source_commit: self._merge_conflict_test_result(
                            context=integration_context,
                            label="integration-merge",
                            command=f"git cherry-pick {source_commit}",
                            merge_result=merge_result,
                            conflicted_files=conflicted_files,
                        ),
                        conflict_message_factory=lambda conflicted_files, merge_result, lineage=lineage, target_step=target_step: (
                            f"{target_step.step_id} failed while merging {lineage.lineage_id}: "
                            f"{', '.join(conflicted_files) or str(getattr(merge_result, 'stderr', '')).strip() or 'unknown conflict'}"
                        ),
                    )
                    if used_merger:
                        merge_block_index += 1

                self._record_context_safe_revision(integration_context)

                _integration_project, _integration_saved, result_step = self._run_saved_execution_step_with_context(
                    context=integration_context,
                    runtime=runtime,
                    step_id=target_step.step_id,
                    allow_push=False,
                )
                if result_step.status != "completed":
                    if integration_info is not None:
                        if isinstance(integration_context, ProjectContext):
                            self.git.abort_cherry_pick(integration_context.paths.repo_dir)
                            self.git.hard_reset(integration_context.paths.repo_dir, pre_join_safe_revision)
                        self._cleanup_integration_worktree(context.paths.repo_dir, integration_info)
                    interrupted = result_step.status == "paused"
                    context.metadata.current_status = self._status_from_plan_state(plan_state) if interrupted else "failed"
                    target_step.status = "paused" if interrupted else "failed"
                    target_step.completed_at = None
                    target_step.commit_hash = None
                    target_step.notes = result_step.notes or (
                        "Immediate stop requested." if interrupted else "Join execution failed."
                    )
                    if interrupted:
                        self._clear_step_failure_metadata(target_step)
                    else:
                        result_reason_code = str((result_step.metadata or {}).get("failure_reason_code", "")).strip() or None
                        self._set_step_failure_metadata(
                            target_step,
                            execution_failure_from_reason(result_reason_code, target_step.notes),
                        )
                    saved = self.save_execution_plan_state(context, plan_state)
                    self.workspace.save_project(context)
                    return context, saved, target_step

                branch_name = str(integration_info.get("branch_name") if integration_info else "").strip()
                self.git.merge_ff_only(context.paths.repo_dir, branch_name)

                integrated_revision = self.git.current_revision(context.paths.repo_dir)
                context.metadata.current_safe_revision = integrated_revision
                context.loop_state.current_safe_revision = integrated_revision
                context.loop_state.last_commit_hash = integrated_revision
                pushed, push_reason = self._push_if_ready(
                    context,
                    context.paths.repo_dir,
                    context.metadata.branch,
                    commit_hash=integrated_revision,
                )

                refreshed = self.load_execution_plan_state(context)
                refreshed_step = next((step for step in refreshed.steps if step.step_id == result_step.step_id), target_step)
                refreshed_step.status = "completed"
                refreshed_step.completed_at = result_step.completed_at or now_utc_iso()
                refreshed_step.commit_hash = integrated_revision
                refreshed_step.notes = result_step.notes or "Join step completed successfully."
                self._clear_step_failure_metadata(refreshed_step)
                if not pushed and push_reason not in {"already_up_to_date"}:
                    refreshed_step.notes = f"{refreshed_step.notes} (push skipped: {push_reason})"
                if pushed or push_reason == "already_up_to_date":
                    remote_cleanup_notes: list[str] = []
                    for candidate_branch in [lineage.branch_name for lineage in merge_lineages] + ([branch_name] if branch_name else []):
                        _deleted, delete_reason = self._delete_remote_branch_if_present(
                            context,
                            context.paths.repo_dir,
                            candidate_branch,
                        )
                        if delete_reason not in {"deleted", "missing_remote_branch", "push_disabled", "missing_remote"}:
                            remote_cleanup_notes.append(f"{candidate_branch}: {delete_reason}")
                    if remote_cleanup_notes:
                        refreshed_step.notes = f"{refreshed_step.notes} (remote cleanup: {'; '.join(remote_cleanup_notes)})"
                saved = self.save_execution_plan_state(context, refreshed)
                context.metadata.current_status = self._status_from_plan_state(saved)

                merged_at = now_utc_iso()
                for lineage in merge_lineages:
                    lineage.status = "merged"
                    lineage.merged_by_step_id = refreshed_step.step_id
                    lineage.updated_at = merged_at
                    lineage.notes = refreshed_step.notes
                    self._cleanup_lineage_worktree(context.paths.repo_dir, lineage)
                if integration_info is not None:
                    self._cleanup_integration_worktree(context.paths.repo_dir, integration_info)
                self._save_lineage_states(context, lineages)
                self.workspace.save_project(context)
                return context, saved, refreshed_step
            except ImmediateStopRequested as exc:
                if integration_context is not None:
                    self.git.abort_cherry_pick(integration_context.paths.repo_dir)
                    self.git.hard_reset(integration_context.paths.repo_dir, pre_join_safe_revision)
                if integration_info is not None:
                    self._cleanup_integration_worktree(context.paths.repo_dir, integration_info)
                context.metadata.current_status = self._status_from_plan_state(plan_state)
                target_step.status = "paused"
                target_step.completed_at = None
                target_step.commit_hash = None
                target_step.notes = str(exc).strip() or "Immediate stop requested."
                self._clear_step_failure_metadata(target_step)
                saved = self.save_execution_plan_state(context, plan_state)
                self.workspace.save_project(context)
                return context, saved, target_step
            except HANDLED_OPERATION_EXCEPTIONS as exc:
                if integration_context is not None:
                    self.git.abort_cherry_pick(integration_context.paths.repo_dir)
                    self.git.hard_reset(integration_context.paths.repo_dir, pre_join_safe_revision)
                if integration_info is not None:
                    self._cleanup_integration_worktree(context.paths.repo_dir, integration_info)
                self.git.hard_reset(context.paths.repo_dir, pre_join_safe_revision)
                context.metadata.current_safe_revision = pre_join_safe_revision
                context.loop_state.current_safe_revision = pre_join_safe_revision
                last_failure_exc = exc if isinstance(exc, ExecutionFailure) else ParallelExecutionFailure(
                    str(exc).strip() or "Join execution failed."
                )
                last_failure_note = str(last_failure_exc)
                if attempt_index >= attempt_limit:
                    context.metadata.current_status = "failed"
                    target_step.status = "failed"
                    target_step.completed_at = None
                    target_step.commit_hash = None
                    target_step.notes = last_failure_note
                    self._set_step_failure_metadata(target_step, last_failure_exc)
                    saved = self.save_execution_plan_state(context, plan_state)
                    self.workspace.save_project(context)
                    return context, saved, target_step
                target_step.status = "running"
                target_step.completed_at = None
                target_step.commit_hash = None
                target_step.notes = (
                    f"Retrying join attempt {attempt_index + 1} of {attempt_limit} after failure: {last_failure_note}"
                )
                self._clear_step_failure_metadata(target_step)
                context.metadata.current_status = f"running:retry-{target_step.step_id.lower()}"
                context.metadata.last_run_at = now_utc_iso()
                plan_state = self.save_execution_plan_state(context, plan_state)
                target_step = next(step for step in plan_state.steps if step.step_id == target_step.step_id)
                self.workspace.save_project(context)
                continue

        context.metadata.current_status = "failed"
        target_step.status = "failed"
        target_step.completed_at = None
        target_step.commit_hash = None
        target_step.notes = last_failure_note or "Join execution failed."
        self._set_step_failure_metadata(
            target_step,
            last_failure_exc or ParallelExecutionFailure(target_step.notes),
        )
        saved = self.save_execution_plan_state(context, plan_state)
        self.workspace.save_project(context)
        return context, saved, target_step

    def _record_context_safe_revision(
        self,
        context: ProjectContext,
        revision: str | None = None,
    ) -> str:
        resolved_revision = str(revision or self.git.current_revision(context.paths.repo_dir)).strip()
        context.metadata.current_safe_revision = resolved_revision
        context.loop_state.current_safe_revision = resolved_revision
        self.workspace.save_project(context)
        return resolved_revision

    def _apply_cherry_pick_with_merger(
        self,
        *,
        context: ProjectContext,
        source_commit: str,
        runner: CodexRunner,
        reporter: Reporter,
        block_index: int,
        candidate: CandidateTask,
        execution_step: ExecutionStep,
        memory_context: str,
        merge_targets: list[str],
        failing_command: str,
        conflict_test_result_factory: Callable[[object, list[str]], TestRunResult],
        conflict_message_factory: Callable[[list[str], object], str],
        post_success_strategy: str = "continue_cherry_pick",
    ) -> tuple[str, bool]:
        merge_result = self.git.try_cherry_pick(context.paths.repo_dir, source_commit)
        if merge_result.returncode == 0:
            return self._record_context_safe_revision(context), False
        if self._is_empty_cherry_pick_result(merge_result):
            if self.git.cherry_pick_in_progress(context.paths.repo_dir):
                self.git.skip_cherry_pick(context.paths.repo_dir)
            return self._record_context_safe_revision(context), False
        conflicted_files = self.git.conflicted_files(context.paths.repo_dir)
        if conflicted_files and self.git.cherry_pick_in_progress(context.paths.repo_dir):
            merge_test_result = conflict_test_result_factory(merge_result, conflicted_files)
            merge_pass_name, merge_run_result, merge_success, merge_commit_hash = self._run_merger_pass(
                context=context,
                runner=runner,
                reporter=reporter,
                block_index=block_index,
                candidate=candidate,
                execution_step=execution_step,
                memory_context=memory_context,
                failing_command=failing_command,
                failing_summary=merge_test_result.summary,
                failing_stdout=read_text(merge_test_result.stdout_file),
                failing_stderr=read_text(merge_test_result.stderr_file),
                merge_targets=merge_targets,
                post_success_strategy=post_success_strategy,
            )
            if merge_run_result.returncode == 0 and merge_success and merge_commit_hash:
                self._log_pass_result(
                    context=context,
                    reporter=reporter,
                    block_index=block_index,
                    candidate=candidate,
                    pass_name=merge_pass_name,
                    run_result=merge_run_result,
                    test_result=None,
                    commit_hash=merge_commit_hash,
                    rollback_status="not_needed",
                    search_enabled=False,
                )
                self._record_context_safe_revision(context, merge_commit_hash)
                return merge_commit_hash, True
        raise ParallelMergeConflictError(conflict_message_factory(conflicted_files, merge_result))

    def _is_empty_cherry_pick_result(self, result: CommandResult) -> bool:
        combined = f"{result.stdout}\n{result.stderr}".lower()
        markers = (
            "the previous cherry-pick is now empty",
            "the patch is empty",
            "nothing to commit",
        )
        return any(marker in combined for marker in markers)

    def _normalize_execution_mode(self, value: str | None) -> str:
        return "parallel"

    def _execution_runtime_options(self, runtime: RuntimeOptions) -> RuntimeOptions:
        execution_model = normalize_step_model(
            str(getattr(runtime, "execution_model", "") or getattr(runtime, "model", "") or getattr(runtime, "model_slug_input", ""))
        )
        if not execution_model:
            return runtime
        payload = runtime.to_dict()
        payload["execution_model"] = execution_model
        payload["model"] = execution_model
        payload["model_slug_input"] = execution_model
        return RuntimeOptions.from_dict(payload)

    def _execution_runtime_preflight_error(self, context: ProjectContext, runtime: RuntimeOptions) -> str:
        execution_runtime = self._execution_runtime_options(runtime)
        return provider_execution_preflight_error(
            str(getattr(execution_runtime, "model_provider", "") or "").strip(),
            codex_path=str(getattr(execution_runtime, "codex_path", "") or "").strip(),
            repo_dir=context.paths.repo_dir,
            provider_api_key_env=str(getattr(execution_runtime, "provider_api_key_env", "") or "").strip(),
            model=str(getattr(execution_runtime, "model", "") or getattr(execution_runtime, "model_slug_input", "")).strip(),
        )

    def _step_model_runtime_overrides(
        self,
        runtime: RuntimeOptions,
        step: ExecutionStep,
    ) -> dict[str, object]:
        choice = resolve_step_model_choice(step, runtime)
        provider = provider_preset(choice.provider)
        previous_provider = str(runtime.model_provider or "").strip().lower()
        current_path = str(runtime.codex_path or "").strip()
        previous_default_path = default_codex_path(previous_provider or "openai")
        if not current_path or previous_provider != choice.provider or current_path == previous_default_path:
            next_path = default_codex_path(choice.provider)
        else:
            next_path = current_path
        next_model = normalize_step_model(choice.model)
        if provider_supports_auto_model(choice.provider) and next_model == "auto":
            next_model_preset = str(runtime.model_preset or "").strip().lower() or (
                "auto" if normalize_reasoning_effort(runtime.effort, fallback="medium") == "medium" else normalize_reasoning_effort(runtime.effort, fallback="medium")
            )
        else:
            next_model_preset = ""
        return {
            "model_provider": choice.provider,
            "local_model_provider": effective_local_model_provider(
                choice.provider,
                str(getattr(runtime, "local_model_provider", "") or "").strip(),
            ),
            "provider_base_url": str(runtime.provider_base_url or "").strip() if previous_provider == choice.provider else provider.default_base_url,
            "provider_api_key_env": str(runtime.provider_api_key_env or "").strip() if previous_provider == choice.provider else provider.default_api_key_env,
            "billing_mode": normalize_billing_mode(
                str(runtime.billing_mode or "") if previous_provider == choice.provider else "",
                choice.provider,
                fallback=provider.default_billing_mode,
            ),
            "codex_path": next_path,
            "model": next_model,
            "model_slug_input": next_model,
            "model_preset": next_model_preset,
            "model_selection_mode": "slug",
            "effort_selection_mode": "auto" if provider_supports_auto_model(choice.provider) and next_model == "auto" else "explicit",
        }

    def _build_execution_step_runtime(
        self,
        runtime: RuntimeOptions,
        step: ExecutionStep,
        *,
        allow_push: bool,
        max_blocks: int,
        require_checkpoint_approval: bool,
        checkpoint_interval_blocks: int,
        execution_mode: str,
        parallel_workers: int | None = None,
        parallel_worker_mode: str | None = None,
        approval_mode: str | None = None,
        sandbox_mode: str | None = None,
    ) -> RuntimeOptions:
        fallback_effort = normalize_reasoning_effort(runtime.effort, fallback="high")
        merged: dict[str, object] = {
            **runtime.to_dict(),
            **self._step_model_runtime_overrides(runtime, step),
            "test_cmd": step.test_command.strip() or runtime.test_cmd,
            "effort": normalize_reasoning_effort(step.reasoning_effort, fallback=fallback_effort),
            "execution_mode": execution_mode,
            "max_blocks": max_blocks,
            "allow_push": allow_push,
            "require_checkpoint_approval": require_checkpoint_approval,
            "checkpoint_interval_blocks": checkpoint_interval_blocks,
        }
        if parallel_workers is not None:
            merged["parallel_workers"] = parallel_workers
        if parallel_worker_mode is not None:
            merged["parallel_worker_mode"] = parallel_worker_mode
        if approval_mode is not None:
            merged["approval_mode"] = approval_mode
        if sandbox_mode is not None:
            merged["sandbox_mode"] = sandbox_mode
        return RuntimeOptions.from_dict(merged)

    def _execution_step_model_selection_source(self, step: ExecutionStep | None) -> str:
        if step is None:
            return ""
        metadata = step.metadata if isinstance(step.metadata, dict) else {}
        source = str(metadata.get("model_selection_source", "")).strip().lower()
        if source in {"auto", "manual"}:
            return source
        return "manual" if str(getattr(step, "model_provider", "") or "").strip() else "auto"

    def _execution_step_lineage_id(self, step: ExecutionStep | None) -> str:
        if step is None:
            return ""
        metadata = step.metadata if isinstance(step.metadata, dict) else {}
        return str(metadata.get("lineage_id", "")).strip()

    def _latest_logged_block_for_lineage(self, block_log_file: Path, lineage_id: str) -> dict[str, object] | None:
        lineage_key = str(lineage_id).strip()
        entries = read_jsonl(block_log_file)
        if not entries:
            return None
        for entry in reversed(entries):
            if not isinstance(entry, dict):
                continue
            if lineage_key and str(entry.get("lineage_id", "")).strip() != lineage_key:
                continue
            return entry
        return None

    def _run_result_failure_detail(self, run_result: CodexRunResult) -> str:
        if run_result.last_message:
            detail = compact_text(str(run_result.last_message).strip(), max_chars=280)
            if detail:
                return detail
        event_detail = self._event_file_failure_detail(run_result)
        if event_detail:
            return event_detail
        attempts = run_result.diagnostics.get("attempts", []) if isinstance(run_result.diagnostics, dict) else []
        generic_detail = ""
        for attempt in reversed(attempts if isinstance(attempts, list) else []):
            if not isinstance(attempt, dict):
                continue
            values = {
                "stderr_excerpt": str(attempt.get("stderr_excerpt") or "").strip(),
                "last_message_excerpt": str(attempt.get("last_message_excerpt") or "").strip(),
                "stdout_excerpt": str(attempt.get("stdout_excerpt") or "").strip(),
            }
            keys = ("stderr_excerpt", "last_message_excerpt", "stdout_excerpt")
            if self._is_generic_empty_output_warning(values["stderr_excerpt"]) and values["stdout_excerpt"]:
                keys = ("stdout_excerpt", "last_message_excerpt", "stderr_excerpt")
            for key in keys:
                detail = compact_text(str(attempt.get(key) or "").strip(), max_chars=280)
                if detail:
                    if self._is_generic_empty_output_warning(detail):
                        generic_detail = generic_detail or detail
                        continue
                    return detail
        return generic_detail

    def _is_generic_empty_output_warning(self, detail: str) -> bool:
        lowered = str(detail or "").strip().lower()
        return "no last agent message" in lowered and "wrote empty content to" in lowered

    def _event_file_failure_detail(self, run_result: CodexRunResult) -> str:
        event_file = getattr(run_result, "event_file", None)
        if not isinstance(event_file, Path) or not event_file.exists():
            return ""
        detail = self._event_log_error_detail(read_text(event_file))
        return compact_text(detail, max_chars=280) if detail else ""

    def _event_log_error_detail(self, event_text: str) -> str:
        for raw_line in reversed(str(event_text or "").splitlines()):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            payload_type = str(payload.get("type", "")).strip().lower()
            if payload_type == "error":
                detail = self._error_message_from_payload_value(payload.get("message"))
                if detail:
                    return detail
            item = payload.get("item")
            if isinstance(item, dict) and str(item.get("type", "")).strip().lower() == "error":
                detail = self._error_message_from_payload_value(item.get("message"))
                if detail:
                    return detail
        return ""

    def _error_message_from_payload_value(self, value: object) -> str:
        message = str(value or "").strip()
        if not message:
            return ""
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            return message
        if not isinstance(payload, dict):
            return message
        error = payload.get("error")
        if isinstance(error, dict):
            nested = str(error.get("message", "")).strip()
            if nested:
                return nested
        nested = str(payload.get("message", "")).strip()
        return nested or message

    def _runtime_error_run_result(
        self,
        *,
        context: ProjectContext,
        pass_type: str,
        block_index: int,
        search_enabled: bool,
        error_detail: str,
    ) -> CodexRunResult:
        pass_slug = str(pass_type or "codex-pass").replace(" ", "_").replace("/", "_")
        block_dir = ensure_dir(context.paths.logs_dir / f"block_{block_index:04d}")
        diagnostics = {
            "attempt_count": 1,
            "unexpected_token_detected": False,
            "recovered_after_retry": False,
            "attempts": [
                {
                    "attempt": 1,
                    "returncode": 1,
                    "unexpected_token_detected": False,
                    "stdout_excerpt": "",
                    "stderr_excerpt": compact_text(str(error_detail or "").strip(), 500),
                    "last_message_excerpt": "",
                    "duration_seconds": 0.0,
                }
            ],
            "synthetic_runtime_error": True,
        }
        return CodexRunResult(
            pass_type=pass_type,
            prompt_file=block_dir / f"{pass_slug}.prompt.md",
            output_file=block_dir / f"{pass_slug}.last_message.txt",
            event_file=block_dir / f"{pass_slug}.events.jsonl",
            returncode=1,
            search_enabled=search_enabled,
            changed_files=[],
            usage={},
            last_message=None,
            attempt_count=1,
            duration_seconds=0.0,
            diagnostics=diagnostics,
        )

    def _provider_fallback_pass_name(self, pass_name: str, provider: str) -> str:
        normalized_pass_name = str(pass_name or "").strip() or "codex-pass"
        provider_slug = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in str(provider or "").strip().lower()).strip("-") or "fallback"
        return f"{normalized_pass_name}-fallback-{provider_slug}"

    def _append_runtime_ui_event(
        self,
        context: ProjectContext,
        event_type: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        payload = {
            "timestamp": now_utc_iso(),
            "event_type": event_type,
            "message": message,
            "details": details or {},
        }
        append_jsonl(context.paths.ui_event_log_file, payload)
        if getattr(context.runtime, "save_project_logs", False):
            append_jsonl(
                context.paths.logs_dir / "project_activity.jsonl",
                {
                    "timestamp": payload["timestamp"],
                    "repo_id": context.metadata.repo_id,
                    "project_dir": str(context.metadata.repo_path),
                    "event_type": event_type,
                    "message": message,
                    "details": payload["details"],
                },
            )

    def _merge_provider_fallback_result(
        self,
        *,
        base_result: CodexRunResult,
        primary_result: CodexRunResult,
        total_attempt_count: int,
        from_provider: str,
        to_provider: str,
        trigger_detail: str,
        chain: list[dict[str, object]],
    ) -> CodexRunResult:
        merged_diagnostics = deepcopy(base_result.diagnostics) if isinstance(base_result.diagnostics, dict) else {}
        merged_diagnostics["provider_fallback"] = {
            "used": True,
            "from_provider": from_provider,
            "to_provider": to_provider,
            "trigger_detail": trigger_detail,
            "previous_returncode": primary_result.returncode,
            "previous_attempt_count": primary_result.attempt_count,
            "previous_diagnostics": deepcopy(primary_result.diagnostics)
            if isinstance(primary_result.diagnostics, dict)
            else primary_result.diagnostics,
            "chain": chain,
        }
        base_result.attempt_count = total_attempt_count
        base_result.diagnostics = merged_diagnostics
        return base_result

    def _retry_run_with_provider_fallback(
        self,
        *,
        context: ProjectContext,
        prompt: str,
        pass_name: str,
        block_index: int,
        search_enabled: bool,
        safe_revision: str,
        run_result: CodexRunResult,
        execution_step: ExecutionStep | None,
        provider_selection_source: str = "",
        reasoning_effort: str | None = None,
    ) -> CodexRunResult:
        failure_detail = self._run_result_failure_detail(run_result)
        if not is_provider_fallbackable_error(failure_detail):
            return run_result

        primary_runtime = context.runtime
        from_provider = normalize_step_model_provider(str(getattr(primary_runtime, "model_provider", "") or "")) or str(getattr(primary_runtime, "model_provider", "") or "").strip() or "unknown"
        fallback_runtimes = build_provider_fallback_runtimes(primary_runtime, current_provider=from_provider)
        if not fallback_runtimes:
            return run_result

        total_attempt_count = run_result.attempt_count
        fallback_chain: list[dict[str, object]] = []
        last_result = run_result

        for fallback_runtime in fallback_runtimes:
            to_provider = normalize_step_model_provider(str(getattr(fallback_runtime, "model_provider", "") or "")) or str(getattr(fallback_runtime, "model_provider", "") or "").strip() or "unknown"
            preflight_error = self._execution_runtime_preflight_error(context, fallback_runtime)
            if preflight_error:
                fallback_chain.append(
                    {
                        "provider": to_provider,
                        "model": str(getattr(fallback_runtime, "model", "") or "").strip(),
                        "local_model_provider": str(getattr(fallback_runtime, "local_model_provider", "") or "").strip(),
                        "returncode": None,
                        "attempt_count": 0,
                        "trigger_detail": preflight_error,
                        "skipped": True,
                    }
                )
                self._append_runtime_ui_event(
                    context,
                    "provider-fallback-skipped",
                    f"Skipped fallback attempt on {to_provider}: {compact_text(preflight_error, max_chars=180)}",
                    {
                        "flow": "execution",
                        "block_index": block_index,
                        "pass_type": pass_name,
                        "step_id": execution_step.step_id if execution_step is not None else "",
                        "from_provider": from_provider,
                        "to_provider": to_provider,
                        "attempt_count": 0,
                        "succeeded": False,
                        "skipped": True,
                        "trigger_detail": compact_text(preflight_error, max_chars=240),
                    },
                )
                continue
            if safe_revision:
                self.git.hard_reset(context.paths.repo_dir, safe_revision)
            self._append_runtime_ui_event(
                context,
                "provider-fallback-started",
                f"Retrying {pass_name} on {to_provider} after {from_provider} failed.",
                {
                    "flow": "execution",
                    "block_index": block_index,
                    "pass_type": pass_name,
                    "step_id": execution_step.step_id if execution_step is not None else "",
                    "from_provider": from_provider,
                    "to_provider": to_provider,
                    "trigger_detail": compact_text(failure_detail, max_chars=240),
                },
            )
            context.runtime = fallback_runtime
            fallback_runner = CodexRunner(context.runtime.codex_path)
            try:
                candidate_result = fallback_runner.run_pass(
                    context=context,
                    prompt=prompt,
                    pass_type=self._provider_fallback_pass_name(pass_name, to_provider),
                    block_index=block_index,
                    search_enabled=search_enabled,
                    reasoning_effort=reasoning_effort,
                )
            except ImmediateStopRequested:
                if safe_revision:
                    self.git.hard_reset(context.paths.repo_dir, safe_revision)
                raise
            except RuntimeError as exc:
                error_detail = str(exc or "").strip()
                candidate_result = self._runtime_error_run_result(
                    context=context,
                    pass_type=self._provider_fallback_pass_name(pass_name, to_provider),
                    block_index=block_index,
                    search_enabled=search_enabled,
                    error_detail=error_detail,
                )
                total_attempt_count += candidate_result.attempt_count
                fallback_chain.append(
                    {
                        "provider": to_provider,
                        "model": str(getattr(fallback_runtime, "model", "") or "").strip(),
                        "local_model_provider": str(getattr(fallback_runtime, "local_model_provider", "") or "").strip(),
                        "returncode": candidate_result.returncode,
                        "attempt_count": candidate_result.attempt_count,
                        "trigger_detail": error_detail,
                    }
                )
                last_result = candidate_result
                self._append_runtime_ui_event(
                    context,
                    "provider-fallback-finished",
                    f"Fallback attempt on {to_provider} failed.",
                    {
                        "flow": "execution",
                        "block_index": block_index,
                        "pass_type": pass_name,
                        "step_id": execution_step.step_id if execution_step is not None else "",
                        "from_provider": from_provider,
                        "to_provider": to_provider,
                        "returncode": candidate_result.returncode,
                        "attempt_count": candidate_result.attempt_count,
                        "succeeded": False,
                        "will_continue": is_provider_fallbackable_error(error_detail),
                        "trigger_detail": compact_text(error_detail, max_chars=240),
                    },
                )
                if is_provider_fallbackable_error(error_detail):
                    continue
                context.runtime = primary_runtime
                return self._merge_provider_fallback_result(
                    base_result=candidate_result,
                    primary_result=run_result,
                    total_attempt_count=total_attempt_count,
                    from_provider=from_provider,
                    to_provider=to_provider,
                    trigger_detail=failure_detail,
                    chain=fallback_chain,
                )

            total_attempt_count += candidate_result.attempt_count
            candidate_detail = self._run_result_failure_detail(candidate_result)
            fallback_chain.append(
                {
                    "provider": to_provider,
                    "model": str(getattr(fallback_runtime, "model", "") or "").strip(),
                    "local_model_provider": str(getattr(fallback_runtime, "local_model_provider", "") or "").strip(),
                    "returncode": candidate_result.returncode,
                    "attempt_count": candidate_result.attempt_count,
                    "trigger_detail": candidate_detail,
                }
            )
            last_result = candidate_result
            candidate_fallbackable = is_provider_fallbackable_error(candidate_detail)
            self._append_runtime_ui_event(
                context,
                "provider-fallback-finished",
                (
                    f"Fallback attempt on {to_provider} succeeded."
                    if candidate_result.returncode == 0
                    else f"Fallback attempt on {to_provider} failed."
                ),
                {
                    "flow": "execution",
                    "block_index": block_index,
                    "pass_type": pass_name,
                    "step_id": execution_step.step_id if execution_step is not None else "",
                    "from_provider": from_provider,
                    "to_provider": to_provider,
                    "returncode": candidate_result.returncode,
                    "attempt_count": candidate_result.attempt_count,
                    "succeeded": candidate_result.returncode == 0,
                    "will_continue": candidate_result.returncode != 0 and candidate_fallbackable,
                    "trigger_detail": compact_text(candidate_detail, max_chars=240),
                },
            )
            if candidate_result.returncode == 0:
                return self._merge_provider_fallback_result(
                    base_result=candidate_result,
                    primary_result=run_result,
                    total_attempt_count=total_attempt_count,
                    from_provider=from_provider,
                    to_provider=to_provider,
                    trigger_detail=failure_detail,
                    chain=fallback_chain,
                )
            if not candidate_fallbackable:
                context.runtime = primary_runtime
                return self._merge_provider_fallback_result(
                    base_result=candidate_result,
                    primary_result=run_result,
                    total_attempt_count=total_attempt_count,
                    from_provider=from_provider,
                    to_provider=to_provider,
                    trigger_detail=failure_detail,
                    chain=fallback_chain,
                )

        context.runtime = primary_runtime
        return self._merge_provider_fallback_result(
            base_result=last_result,
            primary_result=run_result,
            total_attempt_count=total_attempt_count,
            from_provider=from_provider,
            to_provider=str(fallback_chain[-1]["provider"]) if fallback_chain else from_provider,
            trigger_detail=failure_detail,
            chain=fallback_chain,
        )

    def _run_pass_with_provider_fallback(
        self,
        *,
        context: ProjectContext,
        runner: CodexRunner,
        prompt: str,
        pass_type: str,
        block_index: int,
        search_enabled: bool,
        safe_revision: str = "",
        execution_step: ExecutionStep | None = None,
        provider_selection_source: str = "",
        reasoning_effort: str | None = None,
    ) -> CodexRunResult:
        active_runner = runner
        runner_codex_path = getattr(active_runner, "codex_path", None)
        if isinstance(runner_codex_path, str) and runner_codex_path.strip() != str(getattr(context.runtime, "codex_path", "") or "").strip():
            active_runner = CodexRunner(context.runtime.codex_path)
        try:
            run_result = active_runner.run_pass(
                context=context,
                prompt=prompt,
                pass_type=pass_type,
                block_index=block_index,
                search_enabled=search_enabled,
                reasoning_effort=reasoning_effort,
            )
        except ImmediateStopRequested:
            if safe_revision:
                self.git.hard_reset(context.paths.repo_dir, safe_revision)
            raise
        except RuntimeError as exc:
            error_detail = str(exc or "").strip()
            if not is_provider_fallbackable_error(error_detail):
                raise
            run_result = self._runtime_error_run_result(
                context=context,
                pass_type=pass_type,
                block_index=block_index,
                search_enabled=search_enabled,
                error_detail=error_detail,
            )

        if run_result.returncode == 0:
            return run_result
        return self._retry_run_with_provider_fallback(
            context=context,
            prompt=prompt,
            pass_name=pass_type,
            block_index=block_index,
            search_enabled=search_enabled,
            safe_revision=safe_revision,
            run_result=run_result,
            execution_step=execution_step,
            provider_selection_source=provider_selection_source,
            reasoning_effort=reasoning_effort,
        )

    def init_repo(
        self,
        repo_url: str,
        branch: str,
        runtime: RuntimeOptions,
        plan_path: Path | None = None,
        plan_input: str = "",
    ) -> ProjectContext:
        context = self.workspace.initialize_project(repo_url=repo_url, branch=branch, runtime=runtime)
        try:
            self.git.clone_or_update(repo_url, branch, context.paths.repo_dir)
            self.git.configure_local_identity(
                context.paths.repo_dir,
                runtime.git_user_name,
                runtime.git_user_email,
            )
            supplied_plan_text = self._read_supplied_plan_text(plan_path, plan_input)
            if supplied_plan_text and is_plan_markdown(supplied_plan_text):
                plan_text = supplied_plan_text
            else:
                repo_inputs_started_at = perf_counter()
                repo_inputs = self._scan_repository_inputs(context)
                self._log_planning_metric(
                    context,
                    "init_repo_context_scan",
                    started_at=repo_inputs_started_at,
                    flow="planning-bootstrap",
                )
                is_mature, maturity_details = assess_repository_maturity(context.paths.repo_dir, repo_inputs)
                plan_text = self._resolve_plan_text(
                    context=context,
                    runtime=runtime,
                    repo_inputs=repo_inputs,
                    is_mature=is_mature,
                    maturity_details=maturity_details,
                    plan_path=plan_path,
                    plan_input=supplied_plan_text,
                )
            self._write_planning_state(context, runtime, plan_text)
            self._ensure_project_documents(context)

            safe_revision = self.git.current_revision(context.paths.repo_dir)
            context.metadata.current_safe_revision = safe_revision
            context.metadata.last_run_at = now_utc_iso()
            context.metadata.current_status = "ready"
            context.loop_state.current_safe_revision = safe_revision
            self.workspace.save_project(context)
            return context
        except HANDLED_OPERATION_EXCEPTIONS as exc:
            context.metadata.last_run_at = now_utc_iso()
            context.metadata.current_status = "init_failed"
            write_text(context.paths.reports_dir / "init_error.txt", str(exc).strip() + "\n")
            self.workspace.save_project(context)
            raise

    def run(
        self,
        repo_url: str,
        branch: str,
        runtime: RuntimeOptions,
        plan_path: Path | None = None,
        plan_input: str = "",
        work_items: list[str] | None = None,
        resume: bool = False,
    ) -> ProjectContext:
        existing = self.workspace.find_project(repo_url, branch)
        if existing is None:
            context = self.init_repo(
                repo_url,
                branch,
                runtime,
                plan_path=plan_path,
                plan_input=plan_input,
            )
        else:
            context = existing
            context.runtime = runtime
            self.git.clone_or_update(repo_url, branch, context.paths.repo_dir)
            self.git.configure_local_identity(
                context.paths.repo_dir,
                runtime.git_user_name,
                runtime.git_user_email,
            )
            if not resume:
                updated_plan_text = self._read_supplied_plan_text(plan_path, plan_input)
                if updated_plan_text:
                    if is_plan_markdown(updated_plan_text):
                        resolved_plan_text = updated_plan_text
                    else:
                        repo_inputs_started_at = perf_counter()
                        repo_inputs = self._scan_repository_inputs(context)
                        self._log_planning_metric(
                            context,
                            "run_context_scan",
                            started_at=repo_inputs_started_at,
                            flow="planning-bootstrap",
                        )
                        is_mature, maturity_details = assess_repository_maturity(context.paths.repo_dir, repo_inputs)
                        resolved_plan_text = self._resolve_plan_text(
                            context=context,
                            runtime=runtime,
                            repo_inputs=repo_inputs,
                            is_mature=is_mature,
                            maturity_details=maturity_details,
                            plan_path=plan_path,
                            plan_input=updated_plan_text,
                        )
                    self._write_planning_state(context, runtime, resolved_plan_text)

        self._clear_stale_checkpoint_approval_state(context)
        self.workspace.save_project(context)
        runner = CodexRunner(context.runtime.codex_path)
        memory = MemoryStore(context.paths)
        reporter = Reporter(context)
        context.loop_state.stop_requested = False

        block_limit = max(1, context.runtime.max_blocks)
        for _ in range(block_limit):
            if immediate_stop_requested(context):
                context.loop_state.stop_reason = "immediate stop requested"
                context.metadata.current_status = "paused"
                break
            if context.loop_state.stop_requested:
                context.loop_state.stop_reason = "user stop requested"
                context.metadata.current_status = "paused"
                break
            if context.loop_state.pending_checkpoint_approval:
                context.metadata.current_status = "awaiting_checkpoint_approval"
                context.loop_state.stop_reason = "checkpoint approval required"
                break
            stop_reason = self._stop_reason(context)
            if stop_reason:
                context.loop_state.stop_reason = stop_reason
                break
            self._run_single_block(context, runner, memory, reporter, work_items=work_items)
            self.workspace.save_project(context)
            if context.loop_state.stop_reason:
                break

        reporter.write_status_report()
        self.workspace.save_project(context)
        return context

    def run_local(
        self,
        project_dir: Path,
        runtime: RuntimeOptions,
        branch: str = "main",
        origin_url: str = "",
        plan_path: Path | None = None,
        plan_input: str = "",
        work_items: list[str] | None = None,
        resume: bool = False,
        display_name: str = "",
        preserve_repo_state: bool = False,
    ) -> ProjectContext:
        if preserve_repo_state:
            context = self.setup_transient_local_project(
                project_dir=project_dir,
                runtime=runtime,
                branch=branch,
                origin_url=origin_url,
                display_name=display_name,
            )
        else:
            context = self.setup_local_project(
                project_dir=project_dir,
                runtime=runtime,
                branch=branch,
                origin_url=origin_url,
                display_name=display_name,
            )

        context.runtime = runtime
        if not resume:
            updated_plan_text = self._read_supplied_plan_text(plan_path, plan_input)
            if updated_plan_text:
                if is_plan_markdown(updated_plan_text):
                    resolved_plan_text = updated_plan_text
                else:
                    repo_inputs_started_at = perf_counter()
                    repo_inputs = self._scan_repository_inputs(context)
                    self._log_planning_metric(
                        context,
                        "run_local_context_scan",
                        started_at=repo_inputs_started_at,
                        flow="planning-bootstrap",
                    )
                    is_mature, maturity_details = assess_repository_maturity(context.paths.repo_dir, repo_inputs)
                    resolved_plan_text = self._resolve_plan_text(
                        context=context,
                        runtime=runtime,
                        repo_inputs=repo_inputs,
                        is_mature=is_mature,
                        maturity_details=maturity_details,
                        plan_path=plan_path,
                        plan_input=updated_plan_text,
                    )
                self._write_planning_state(context, runtime, resolved_plan_text)

        self._clear_stale_checkpoint_approval_state(context)
        self.workspace.save_project(context)
        runner = CodexRunner(context.runtime.codex_path)
        memory = MemoryStore(context.paths)
        reporter = Reporter(context)
        context.loop_state.stop_requested = False

        block_limit = max(1, context.runtime.max_blocks)
        for _ in range(block_limit):
            if immediate_stop_requested(context):
                context.loop_state.stop_reason = "immediate stop requested"
                context.metadata.current_status = "paused"
                break
            if context.loop_state.stop_requested:
                context.loop_state.stop_reason = "user stop requested"
                context.metadata.current_status = "paused"
                break
            if context.loop_state.pending_checkpoint_approval:
                context.metadata.current_status = "awaiting_checkpoint_approval"
                context.loop_state.stop_reason = "checkpoint approval required"
                break
            stop_reason = self._stop_reason(context)
            if stop_reason:
                context.loop_state.stop_reason = stop_reason
                break
            self._run_single_block(context, runner, memory, reporter, work_items=work_items)
            self.workspace.save_project(context)
            if context.loop_state.stop_reason:
                break

        reporter.write_status_report()
        self.workspace.save_project(context)
        return context

    def resume(self, repo_url: str, branch: str, runtime: RuntimeOptions, work_items: list[str] | None = None) -> ProjectContext:
        return self.run(repo_url=repo_url, branch=branch, runtime=runtime, work_items=work_items, resume=True)

    def list_projects(self) -> list[ProjectContext]:
        return self.workspace.list_projects()

    def local_project(self, project_dir: Path) -> ProjectContext | None:
        return self.workspace.find_project_by_repo_path(project_dir)

    def status(self, repo_url: str, branch: str) -> ProjectContext:
        context = self.workspace.find_project(repo_url, branch)
        if context is None:
            raise KeyError(f"Repository {repo_url} [{branch}] is not managed in this workspace.")
        return context

    def history(self, repo_url: str, branch: str, limit: int = 10) -> str:
        context = self.status(repo_url, branch)
        return Reporter(context).render_history(limit=limit)

    def report(self, repo_url: str, branch: str) -> Path:
        context = self.status(repo_url, branch)
        return Reporter(context).write_status_report()

    def logx(
        self,
        repo_url: str,
        branch: str,
        max_artifacts: int = 400,
        source_repo_dir: Path | None = None,
    ) -> Path:
        source_root = source_repo_dir.resolve() if source_repo_dir is not None else None
        if source_root is not None and not source_root.exists():
            raise FileNotFoundError(f"Source repository directory not found: {source_root}")

        if repo_url:
            context = self.status(repo_url, branch)
        else:
            if source_root is None:
                raise ValueError("logx requires either a repo URL/path or a source repository directory")
            context = self.workspace.find_project_by_repo_path(source_root)
            if context is None:
                context = self.workspace.initialize_local_project(
                    project_dir=source_root,
                    branch=branch,
                    runtime=RuntimeOptions(),
                    origin_url="",
                    display_name=source_root.name,
                )
            context.metadata.branch = branch
            context.metadata.current_status = "setup_ready"
            self.workspace.save_project(context)

        return Reporter(context).write_logx(
            max_artifacts=max_artifacts,
            source_repo_dir=source_root,
        )

    def plan_work(
        self,
        repo_url: str,
        branch: str,
        runtime: RuntimeOptions,
        plan_path: Path | None = None,
        plan_input: str = "",
    ) -> dict[str, object]:
        repo_inputs: dict[str, str] | None = None
        existing = self.workspace.find_project(repo_url, branch)
        if existing is None:
            context = self.init_repo(
                repo_url=repo_url,
                branch=branch,
                runtime=runtime,
                plan_path=plan_path,
                plan_input=plan_input,
            )
        else:
            context = existing
            context.runtime = runtime
            self.git.clone_or_update(repo_url, branch, context.paths.repo_dir)
            self.git.configure_local_identity(
                context.paths.repo_dir,
                runtime.git_user_name,
                runtime.git_user_email,
            )
            supplied_plan_text = self._read_supplied_plan_text(plan_path, plan_input)
            if supplied_plan_text:
                if is_plan_markdown(supplied_plan_text):
                    plan_text = supplied_plan_text
                else:
                    repo_inputs_started_at = perf_counter()
                    repo_inputs = self._scan_repository_inputs(context)
                    self._log_planning_metric(
                        context,
                        "plan_work_context_scan",
                        started_at=repo_inputs_started_at,
                        flow="planning-bootstrap",
                    )
                    is_mature, maturity_details = assess_repository_maturity(context.paths.repo_dir, repo_inputs)
                    plan_text = self._resolve_plan_text(
                        context=context,
                        runtime=runtime,
                        repo_inputs=repo_inputs,
                        is_mature=is_mature,
                        maturity_details=maturity_details,
                        plan_path=plan_path,
                        plan_input=supplied_plan_text,
                    )
            elif context.paths.plan_file.exists():
                plan_text = read_text(context.paths.plan_file)
            else:
                repo_inputs_started_at = perf_counter()
                repo_inputs = self._scan_repository_inputs(context)
                self._log_planning_metric(
                    context,
                    "plan_work_context_scan",
                    started_at=repo_inputs_started_at,
                    flow="planning-bootstrap",
                )
                is_mature, maturity_details = assess_repository_maturity(context.paths.repo_dir, repo_inputs)
                plan_text = self._resolve_plan_text(
                    context=context,
                    runtime=runtime,
                    repo_inputs=repo_inputs,
                    is_mature=is_mature,
                    maturity_details=maturity_details,
                    plan_path=plan_path,
                    plan_input="",
                )
            self._write_planning_state(context, runtime, plan_text)
            self.workspace.save_project(context)

        plan_text = read_text(context.paths.plan_file)
        runner = CodexRunner(context.runtime.codex_path)
        mid_items, mid_term_text = self._plan_block_items(
            context=context,
            runner=runner,
            plan_text=plan_text,
            work_items=None,
            max_items=max(3, min(context.runtime.max_blocks, 6)),
            repo_inputs=repo_inputs,
        )
        write_text(context.paths.mid_term_plan_file, mid_term_text)
        current_step = context.loop_state.block_index + (1 if context.metadata.current_status.startswith("running:") else 0)
        steps: list[dict[str, object]] = []
        for index, item in enumerate(mid_items, start=1):
            state = "pending"
            if current_step <= 0 and index == 1:
                state = "current"
            elif index <= context.loop_state.block_index:
                state = "done"
            elif index == current_step:
                state = "current"
            steps.append(
                {
                    "index": index,
                    "label": f"B{index}",
                    "title": item.text,
                    "refs": [item.item_id] if item.item_id.startswith("PL") else [],
                    "state": state,
                }
            )
        return {
            "repo_slug": context.metadata.slug,
            "current_status": context.metadata.current_status,
            "block_index": context.loop_state.block_index,
            "max_blocks": context.runtime.max_blocks,
            "strict_validation": "각 pass 후 테스트, 실패 시 즉시 rollback, safe revision만 유지",
            "steps": steps,
        }

    def checkpoints(self, repo_url: str, branch: str) -> dict:
        context = self.status(repo_url, branch)
        data = read_json(context.paths.checkpoint_state_file, default=None)
        needs_write = data is None
        if data is None:
            checkpoints = build_checkpoint_timeline(read_text(context.paths.plan_file), context.runtime.checkpoint_interval_blocks)
            data = {"checkpoints": [checkpoint.to_dict() for checkpoint in checkpoints]}
            write_text(context.paths.checkpoint_timeline_file, checkpoint_timeline_markdown(checkpoints))
        if not isinstance(data, dict):
            data = {"checkpoints": []}
            needs_write = True
        checkpoint_items = data.get("checkpoints", [])
        reconciled_items, changed = reconcile_checkpoint_items_from_blocks(
            checkpoint_items if isinstance(checkpoint_items, list) else [],
            read_jsonl(context.paths.block_log_file),
        )
        data = dict(data)
        data["checkpoints"] = reconciled_items
        if changed:
            needs_write = True
        if needs_write:
            write_json(context.paths.checkpoint_state_file, data)
            write_text(
                context.paths.checkpoint_timeline_file,
                checkpoint_timeline_markdown([Checkpoint.from_dict(item) for item in reconciled_items]),
            )
        return data

    def approve_checkpoint(self, repo_url: str, branch: str, review_notes: str = "", push: bool = True) -> dict:
        context = self.status(repo_url, branch)
        data = self.checkpoints(repo_url, branch)
        checkpoints = data.get("checkpoints", [])
        active_lineage_id = str(context.loop_state.current_checkpoint_lineage_id or "").strip()
        target: dict | None = next(
            (
                checkpoint
                for checkpoint in checkpoints
                if checkpoint.get("status") == "awaiting_review"
                and active_lineage_id
                and str(checkpoint.get("lineage_id", "")).strip() == active_lineage_id
            ),
            None,
        )
        if target is None:
            target = next(
                (
                    checkpoint
                    for checkpoint in checkpoints
                    if checkpoint.get("status") == "awaiting_review"
                    and not str(checkpoint.get("lineage_id", "")).strip()
                ),
                None,
            )
        if target is None and context.loop_state.current_checkpoint_id:
            target = next(
                (
                    checkpoint
                    for checkpoint in checkpoints
                    if checkpoint.get("checkpoint_id") == context.loop_state.current_checkpoint_id
                    and (
                        not active_lineage_id
                        or not str(checkpoint.get("lineage_id", "")).strip()
                        or str(checkpoint.get("lineage_id", "")).strip() == active_lineage_id
                    )
                ),
                None,
            )
        if target is None:
            raise RuntimeError("No checkpoint is awaiting approval.")
        target["status"] = "approved"
        target["approved_at"] = now_utc_iso()
        target["review_notes"] = review_notes.strip()
        if push:
            pushed, push_reason = self._push_if_ready(
                context,
                context.paths.repo_dir,
                context.metadata.branch,
                commit_hash=context.metadata.current_safe_revision or "",
            )
            target["pushed"] = pushed
            if not pushed:
                target["push_skipped_reason"] = push_reason
        else:
            target["pushed"] = False
            target["push_skipped_reason"] = "not_requested"
        write_json(context.paths.checkpoint_state_file, data)
        plan_state = self.load_execution_plan_state(context)
        context.loop_state.current_checkpoint_id = None
        context.loop_state.current_checkpoint_lineage_id = None
        context.loop_state.pending_checkpoint_approval = False
        context.loop_state.stop_requested = False
        context.loop_state.stop_reason = None
        context.metadata.current_status = self._status_from_plan_state(plan_state)
        self.workspace.save_project(context)
        return target

    def request_stop(self, repo_url: str, branch: str) -> dict[str, str]:
        context = self.status(repo_url, branch)
        context.loop_state.stop_requested = True
        context.loop_state.stop_reason = "user stop requested"
        self.workspace.save_project(context)
        return {"status": "stop_requested"}














    def _ensure_project_documents(self, context: ProjectContext) -> None:
        ensure_dir(context.paths.review_dir)
        ensure_dir(context.paths.ml_experiment_reports_dir)
        ensure_dir(context.paths.lineage_manifests_dir)
        ensure_contract_wave_artifacts(context.paths)
        for file_path, starter in [
            (context.paths.active_task_file, "# Active Task\n\nNo active task selected yet.\n"),
            (context.paths.block_review_file, "# Block Review\n\nNo completed blocks yet.\n"),
            (context.paths.research_notes_file, "# Research Notes\n\nNo research notes recorded yet.\n"),
            (context.paths.attempt_history_file, "# Attempt History\n\n"),
            (context.paths.closeout_report_file, "# Closeout Report\n\nNo closeout has been run yet.\n"),
            (context.paths.ml_experiment_report_file, "# ML Experiment Report\n\nNo ML experiment summary has been generated yet.\n"),
        ]:
            if not file_path.exists():
                write_text(file_path, starter)
        if not context.paths.scope_guard_file.exists():
            write_text(context.paths.scope_guard_file, ensure_scope_guard(context))
        if not context.paths.execution_plan_file.exists():
            write_json(
                context.paths.execution_plan_file,
                ExecutionPlanState(
                    workflow_mode=normalize_workflow_mode(context.runtime.workflow_mode),
                    default_test_command=context.runtime.test_cmd,
                ).to_dict(),
            )
        if not context.paths.ml_mode_state_file.exists():
            write_json(context.paths.ml_mode_state_file, self._default_ml_mode_state(context).to_dict())
        if not context.paths.ml_experiment_results_svg_file.exists():
            write_text(context.paths.ml_experiment_results_svg_file, self._ml_results_svg([]))

    def _execution_step_rationale(self, step: ExecutionStep, test_command: str) -> str:
        normalize_execution_step_policy(step)
        details = step.codex_description or step.display_description or "Complete the saved execution checkpoint with a small, safe change."
        success = step.success_criteria or "The verification command exits successfully."
        ui_hint = step.display_description.strip()
        dependency_hint = f" Dependencies: {', '.join(step.depends_on)}." if step.depends_on else ""
        ownership_hint = f" Owned paths: {', '.join(step.owned_paths)}." if step.owned_paths else ""
        step_kind = self._step_kind(step)
        kind_hint = ""
        if step_kind != "task":
            kind_hint = f" Step kind: {step_kind}."
        policy_hint = f" Policy: {policy_summary(step)}."
        metadata_hint = ""
        if step.metadata:
            metadata_hint = f" Metadata: {json.dumps(step.metadata, ensure_ascii=False, sort_keys=True)}."
        if ui_hint and ui_hint != details:
            return f"UI description: {ui_hint}. Execution instruction: {details}.{kind_hint}{dependency_hint}{ownership_hint}{policy_hint}{metadata_hint} Verification command: {test_command}. Success criteria: {success}"
        return f"{details}.{kind_hint}{dependency_hint}{ownership_hint}{policy_hint}{metadata_hint} Verification command: {test_command}. Success criteria: {success}"

    def _all_steps_completed(self, steps: list[ExecutionStep]) -> bool:
        return bool(steps) and all(step.status == "completed" for step in steps)

    def _status_from_plan_state(self, plan_state: ExecutionPlanState) -> str:
        return status_from_plan_state(plan_state)

    def _checkpoints_from_execution_steps(self, steps: list[ExecutionStep]) -> list[Checkpoint]:
        checkpoints: list[Checkpoint] = []
        for index, step in enumerate(steps, start=1):
            status = "pending"
            if step.status == "completed":
                status = "approved"
            elif step.status in {"running", "integrating"}:
                status = "running"
            elif step.status in {"failed", "paused"}:
                status = step.status
            checkpoints.append(
                Checkpoint(
                    checkpoint_id=f"CP{index}",
                    title=step.title,
                    plan_refs=[step.step_id],
                    target_block=index,
                    deadline_at=str(step.deadline_at or "").strip(),
                    status=status,
                    created_at=step.started_at or now_utc_iso(),
                    reached_at=step.completed_at if step.status == "completed" else step.started_at,
                    lineage_id=self._execution_step_lineage_id(step),
                    approved_at=step.completed_at if step.status == "completed" else None,
                    review_notes=step.notes,
                    commit_hashes=[step.commit_hash] if step.commit_hash else [],
                    pushed=bool(step.commit_hash),
                )
            )
        return checkpoints

    def _run_single_block(
        self,
        context: ProjectContext,
        runner: CodexRunner,
        memory: MemoryStore,
        reporter: Reporter,
        work_items: list[str] | None = None,
        candidate_override: CandidateTask | None = None,
        execution_step_override: ExecutionStep | None = None,
        suppress_failure_reporting: bool = False,
    ) -> None:
        context.loop_state.block_index += 1
        block_index = context.loop_state.block_index
        context.metadata.current_status = f"running:block:{block_index}"
        context.metadata.last_run_at = now_utc_iso()
        if str(getattr(context.metadata, "local_logs_mode", "repo") or "repo").strip().lower() == "repo":
            ensure_gitignore(context.paths.repo_dir)
        safe_revision = context.metadata.current_safe_revision or self.git.current_revision(context.paths.repo_dir)

        if candidate_override is None:
            plan_text = read_text(context.paths.plan_file)
            remaining_limit = max(1, context.runtime.max_blocks - block_index + 1)
            mid_items, mid_term_text = self._plan_block_items(
                context=context,
                runner=runner,
                plan_text=plan_text,
                work_items=work_items,
                max_items=min(remaining_limit, 6),
            )
            write_text(context.paths.mid_term_plan_file, mid_term_text)
            memory_context = memory.render_context(mid_term_text)
            candidates = candidate_tasks_from_mid_term(mid_items, memory_context)
            selected = select_candidate(candidates)
            context.loop_state.last_candidates = [candidate.to_dict() for candidate in candidates]
        else:
            selected = candidate_override
            mid_term_text, _ = build_mid_term_plan_from_plan_items(
                execution_steps_to_plan_items(
                    [
                        ExecutionStep(
                            step_id=selected.plan_refs[0] if selected.plan_refs else f"ST{block_index}",
                            title=selected.title,
                            test_command=context.runtime.test_cmd,
                        )
                    ]
                ),
                "This block follows the user-reviewed execution step.",
            )
            write_text(context.paths.mid_term_plan_file, mid_term_text)
            memory_context = memory.render_context(mid_term_text)
            context.loop_state.last_candidates = [selected.to_dict()]
        context.loop_state.current_task = selected.title
        write_active_task(context, selected, memory_context)

        block_commit_hashes: list[str] = []
        block_changed_files: list[str] = []
        selected_task = selected.title

        if context.loop_state.stop_requested:
            context.loop_state.stop_reason = "user stop requested"
            context.metadata.current_status = "ready"
            return
        search_pass, search_tests, search_commit = self._execute_pass(
            context=context,
            runner=runner,
            reporter=reporter,
            block_index=block_index,
            candidate=selected,
            pass_name="block-search-pass",
            safe_revision=safe_revision,
            search_enabled=True,
            memory_context_override=memory_context,
            execution_step=execution_step_override,
        )
        block_changed_files.extend(search_pass.changed_files)
        if search_tests is None:
            guard_failure = self._guard_failure_from_run_result(search_pass)
            regression_failure = search_pass.returncode == 0 and guard_failure is None
            no_progress_failure = guard_failure is not None and guard_failure[0] in {"no_changed_files", "out_of_scope_changes"}
            if guard_failure is not None:
                failure = execution_failure_from_reason(guard_failure[0], guard_failure[1])
            else:
                failure = (
                    VerificationTestFailure("Search-enabled Codex pass regressed tests and was rolled back.")
                    if regression_failure
                    else AgentPassExecutionError(self._codex_failure_note(selected_task, search_pass))
                )
            failure_summary = str(failure)
            if regression_failure:
                context.loop_state.counters.regression_failures += 1
                context.loop_state.stop_reason = self._stop_reason(context)
            elif no_progress_failure:
                context.loop_state.counters.no_progress_blocks += 1
                context.loop_state.counters.empty_cycles += 1
                context.loop_state.stop_reason = self._stop_reason(context)
            else:
                context.loop_state.stop_reason = failure_summary
            memory.record_failure(
                task=selected_task,
                summary=failure_summary,
                tags=(
                    ["search", "regression"]
                    if regression_failure
                    else (["search", "guard_failure"] if guard_failure is not None else ["search", "codex_failure"])
                ),
                block_index=block_index,
                commit_hash=None,
            )
            reporter.write_block_review(
                reflection_markdown(selected_task, "Search-enabled pass failed; rolled back.", [], [])
            )
            reporter.append_attempt_history(
                attempt_history_entry(block_index, selected_task, "search pass rolled back", [])
            )
            reporter.log_block(
                {
                    "repository_id": context.metadata.repo_id,
                    "repository_slug": context.metadata.slug,
                    "block_index": block_index,
                    "lineage_id": self._execution_step_lineage_id(execution_step_override) or None,
                    "status": "rolled_back",
                    "selected_task": selected_task,
                    "changed_files": [],
                    "test_summary": failure_summary,
                    "commit_hashes": [],
                    "rollback_status": "rolled_back_to_safe_revision",
                    **failure_log_fields(failure),
                }
            )
            if not suppress_failure_reporting:
                self._report_failure(
                    context,
                    reporter,
                    failure_type="block_failed",
                    summary=failure_summary,
                    block_index=block_index,
                    selected_task=selected_task,
                )
            return
        if search_commit:
            block_commit_hashes.append(search_commit)
            context.metadata.current_safe_revision = search_commit
            context.loop_state.current_safe_revision = search_commit

        test_summary = search_tests.summary if search_tests else "No search-enabled test run."
        if block_commit_hashes:
            pushed, push_reason = self._push_if_ready(
                context,
                context.paths.repo_dir,
                context.metadata.branch,
                commit_hash=block_commit_hashes[-1],
            )
            if not pushed and push_reason not in {"already_up_to_date"}:
                test_summary = f"{test_summary}\n\nPush skipped: {push_reason}"

        made_progress = bool(block_commit_hashes)
        if made_progress:
            context.loop_state.counters.no_progress_blocks = 0
            context.loop_state.counters.empty_cycles = 0
        else:
            context.loop_state.counters.no_progress_blocks += 1
            context.loop_state.counters.empty_cycles += 1

        reporter.write_block_review(
            reflection_markdown(selected_task, test_summary, sorted(set(block_changed_files)), block_commit_hashes)
        )
        reporter.append_attempt_history(
            attempt_history_entry(
                block_index,
                selected_task,
                "completed" if made_progress else "completed with no committed changes",
                block_commit_hashes,
            )
        )
        memory.record_task_summary(
            task=selected_task,
            summary=test_summary,
            tags=["task-summary"],
            block_index=block_index,
            commit_hash=block_commit_hashes[-1] if block_commit_hashes else None,
        )
        if made_progress:
            memory.record_success(
                task=selected_task,
                summary="Completed block with one search-enabled Codex pass.",
                tags=["search", "implementation"],
                block_index=block_index,
                commit_hash=block_commit_hashes[-1],
            )
        reporter.log_block(
            {
                "repository_id": context.metadata.repo_id,
                "repository_slug": context.metadata.slug,
                "block_index": block_index,
                "lineage_id": self._execution_step_lineage_id(execution_step_override) or None,
                "status": "completed",
                "selected_task": selected_task,
                "changed_files": sorted(set(block_changed_files)),
                "test_summary": test_summary,
                "commit_hashes": block_commit_hashes,
                "rollback_status": "not_needed",
            }
        )
        context.loop_state.last_commit_hash = block_commit_hashes[-1] if block_commit_hashes else context.loop_state.last_commit_hash
        context.loop_state.last_block_completed_at = now_utc_iso()
        if made_progress:
            self._mark_checkpoint_if_due(
                context,
                block_index,
                block_commit_hashes,
                lineage_id=self._execution_step_lineage_id(execution_step_override),
            )
        if context.loop_state.pending_checkpoint_approval:
            context.metadata.current_status = "awaiting_checkpoint_approval"
            context.loop_state.stop_reason = "checkpoint approval required"
        else:
            context.metadata.current_status = "ready"
            context.loop_state.stop_reason = self._stop_reason(context)



















    def _execute_pass(
        self,
        context: ProjectContext,
        runner: CodexRunner,
        reporter: Reporter,
        block_index: int,
        candidate: CandidateTask,
        pass_name: str,
        safe_revision: str,
        search_enabled: bool,
        memory_context_override: str | None = None,
        execution_step: ExecutionStep | None = None,
    ) -> tuple:
        memory_context = memory_context_override or "No additional memory context."
        execution_prompt_template = load_step_execution_prompt_template(
            context.runtime.execution_mode,
            normalize_workflow_mode(context.runtime.workflow_mode),
        )
        prompt = implementation_prompt(
            context=context,
            candidate=candidate,
            memory_context=memory_context,
            pass_name=pass_name,
            execution_step=execution_step,
            template_text=execution_prompt_template,
        )
        run_result = self._run_pass_with_provider_fallback(
            context=context,
            runner=runner,
            prompt=prompt,
            pass_type=pass_name,
            block_index=block_index,
            search_enabled=search_enabled,
            safe_revision=safe_revision,
            execution_step=execution_step,
        )
        reverted_housekeeping = self._revert_housekeeping_changes(context, execution_step)
        run_result.changed_files = self.git.changed_files(context.paths.repo_dir)
        if reverted_housekeeping:
            diagnostics = run_result.diagnostics if isinstance(run_result.diagnostics, dict) else {}
            diagnostics["reverted_housekeeping_paths"] = reverted_housekeeping
            run_result.diagnostics = diagnostics
        if run_result.returncode != 0:
            self.git.hard_reset(context.paths.repo_dir, safe_revision)
            self._log_pass_result(
                context=context,
                reporter=reporter,
                block_index=block_index,
                candidate=candidate,
                pass_name=pass_name,
                run_result=run_result,
                test_result=None,
                commit_hash=None,
                rollback_status="rolled_back_to_safe_revision",
                search_enabled=search_enabled,
            )
            return run_result, None, None

        try:
            test_result = self._run_test_command(
                context,
                block_index,
                pass_name,
                state_fingerprint=self._current_verify_state_fingerprint(context, run_result.changed_files),
            )
        except ImmediateStopRequested:
            self.git.hard_reset(context.paths.repo_dir, safe_revision)
            raise
        guard_failure = self._verification_output_guard_failure(test_result)
        if guard_failure is None and test_result.returncode == 0:
            guard_failure = self._step_scope_guard_failure(execution_step, run_result.changed_files)
        if guard_failure is not None:
            guard_reason_code, guard_message, _guard_skip_debugger = guard_failure
            self._apply_guard_failure(
                run_result,
                test_result,
                reason_code=guard_reason_code,
                message=guard_message,
            )
        reporter.save_test_result(block_index, pass_name, test_result)
        commit_hash: str | None = None
        rollback_status = "not_needed"
        if test_result.returncode != 0:
            debugger_skip_reason = self._debugger_skip_reason(
                changed_files=run_result.changed_files,
                test_result=test_result,
                guard_failure_reason=guard_failure[0] if guard_failure is not None and guard_failure[2] else None,
            )
            self._log_pass_result(
                context=context,
                reporter=reporter,
                block_index=block_index,
                candidate=candidate,
                pass_name=pass_name,
                run_result=run_result,
                test_result=test_result,
                commit_hash=None,
                rollback_status=f"debugger_skipped_{debugger_skip_reason}" if debugger_skip_reason else "debugger_invoked",
                search_enabled=search_enabled,
            )
            if debugger_skip_reason:
                self.git.hard_reset(context.paths.repo_dir, safe_revision)
                return run_result, None, None
            try:
                debug_pass_name, debug_run_result, debug_test_result, debug_commit_hash = self._run_debugger_pass(
                    context=context,
                    runner=runner,
                    reporter=reporter,
                    block_index=block_index,
                    candidate=candidate,
                    execution_step=execution_step,
                    memory_context=memory_context,
                    failing_pass_name=pass_name,
                    failing_test_result=test_result,
                )
            except ImmediateStopRequested:
                self.git.hard_reset(context.paths.repo_dir, safe_revision)
                raise
            run_result.changed_files = sorted(set(run_result.changed_files + debug_run_result.changed_files))
            debug_rollback_status = "not_needed"
            if debug_run_result.returncode != 0 or debug_test_result is None or debug_test_result.returncode != 0:
                self.git.hard_reset(context.paths.repo_dir, safe_revision)
                rollback_status = "rolled_back_to_safe_revision"
                debug_rollback_status = rollback_status
                self._log_pass_result(
                    context=context,
                    reporter=reporter,
                    block_index=block_index,
                    candidate=candidate,
                    pass_name=debug_pass_name,
                    run_result=debug_run_result,
                    test_result=debug_test_result,
                    commit_hash=None,
                    rollback_status=debug_rollback_status,
                    search_enabled=False,
                )
                return run_result, None, None
            self._log_pass_result(
                context=context,
                reporter=reporter,
                block_index=block_index,
                candidate=candidate,
                pass_name=debug_pass_name,
                run_result=debug_run_result,
                test_result=debug_test_result,
                commit_hash=debug_commit_hash,
                rollback_status=debug_rollback_status,
                search_enabled=False,
            )
            return run_result, debug_test_result, debug_commit_hash
        elif self.git.has_changes(context.paths.repo_dir):
            commit_descriptor = build_commit_descriptor(
                context,
                pass_name,
                candidate.title,
                execution_step=execution_step,
            )
            commit_hash = self.git.commit_all(
                context.paths.repo_dir,
                commit_descriptor.message,
                author_name=commit_descriptor.author_name,
            )
        self._log_pass_result(
            context=context,
            reporter=reporter,
            block_index=block_index,
            candidate=candidate,
            pass_name=pass_name,
            run_result=run_result,
            test_result=test_result,
            commit_hash=commit_hash,
            rollback_status=rollback_status,
            search_enabled=search_enabled,
        )
        return run_result, test_result, commit_hash

    def _run_test_command(
        self,
        context: ProjectContext,
        block_index: int,
        label: str,
        *,
        state_fingerprint: str | None = None,
    ) -> TestRunResult:
        return self.verification.run(
            context=context,
            block_index=block_index,
            label=label,
            command=context.runtime.test_cmd,
            state_fingerprint=state_fingerprint,
        )

    def _stop_reason(self, context: ProjectContext) -> str | None:
        counters = context.loop_state.counters
        if counters.no_progress_blocks >= context.runtime.no_progress_limit:
            return f"no progress for {counters.no_progress_blocks} block(s)"
        if counters.regression_failures >= context.runtime.regression_limit:
            return f"repeated regression failures: {counters.regression_failures}"
        if counters.empty_cycles >= context.runtime.empty_cycle_limit:
            return f"too many empty cycles: {counters.empty_cycles}"
        return None

    def _mark_checkpoint_if_due(
        self,
        context: ProjectContext,
        block_index: int,
        commit_hashes: list[str],
        *,
        lineage_id: str = "",
    ) -> None:
        if not context.runtime.require_checkpoint_approval:
            return
        data = read_json(context.paths.checkpoint_state_file, default={"checkpoints": []})
        checkpoints = data.get("checkpoints", [])
        changed = False
        lineage_key = str(lineage_id).strip()
        def _eligible(checkpoint: dict[str, object], *, exact: bool) -> bool:
            if checkpoint.get("status") != "pending":
                return False
            if int(checkpoint.get("target_block", 0)) > block_index:
                return False
            checkpoint_lineage = str(checkpoint.get("lineage_id", "")).strip()
            if exact:
                return bool(lineage_key) and checkpoint_lineage == lineage_key
            return not checkpoint_lineage

        checkpoint = next((item for item in checkpoints if _eligible(item, exact=True)), None)
        if checkpoint is None:
            checkpoint = next((item for item in checkpoints if _eligible(item, exact=False)), None)
        if checkpoint is not None:
            checkpoint["status"] = "awaiting_review"
            checkpoint["reached_at"] = now_utc_iso()
            checkpoint["commit_hashes"] = commit_hashes
            if lineage_key:
                checkpoint["lineage_id"] = lineage_key
            context.loop_state.current_checkpoint_id = checkpoint.get("checkpoint_id")
            context.loop_state.current_checkpoint_lineage_id = str(checkpoint.get("lineage_id", "")).strip() or None
            context.loop_state.pending_checkpoint_approval = True
            changed = True
        if changed:
            write_json(context.paths.checkpoint_state_file, data)

    def _clear_stale_checkpoint_approval_state(self, context: ProjectContext) -> None:
        if context.runtime.require_checkpoint_approval:
            return

        data = read_json(context.paths.checkpoint_state_file, default=None)
        checkpoints = data.get("checkpoints", []) if isinstance(data, dict) else []
        changed = False
        cleared_at = now_utc_iso()

        for checkpoint in checkpoints:
            if checkpoint.get("status") != "awaiting_review":
                continue
            checkpoint["status"] = "approved"
            checkpoint["approved_at"] = checkpoint.get("approved_at") or cleared_at
            checkpoint["pushed"] = False
            checkpoint["push_skipped_reason"] = checkpoint.get("push_skipped_reason") or "approval_disabled"
            checkpoint["review_notes"] = checkpoint.get("review_notes") or "Checkpoint approval requirement was disabled."
            changed = True

        if changed and isinstance(data, dict):
            write_json(context.paths.checkpoint_state_file, data)

        if context.loop_state.current_checkpoint_id or context.loop_state.pending_checkpoint_approval:
            context.loop_state.current_checkpoint_id = None
            context.loop_state.current_checkpoint_lineage_id = None
            context.loop_state.pending_checkpoint_approval = False
            if context.loop_state.stop_reason == "checkpoint approval required":
                context.loop_state.stop_reason = None

    def _parallel_conflict_details(self, conflicted_files: list[str]) -> dict[str, object]:
        files = sorted({str(item).strip() for item in conflicted_files if str(item).strip()})
        return {
            "policy": "attempt_debugger_recovery_then_report",
            "recommended_action": "automatic_merge_debugger",
            "files": files,
            "procedure": (
                "Hand merge conflicts to the parallel merge debugger first so it can resolve the final merged code intentionally. "
                "If recovery still fails, keep the base branch safe revision, inspect each conflicted file intentionally, "
                "then rerun the batch after the overlap is resolved."
            ),
        }

    def _merge_conflict_test_result(
        self,
        *,
        context: ProjectContext,
        label: str,
        command: str,
        merge_result,
        conflicted_files: list[str],
    ) -> TestRunResult:
        normalized_label = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in label.strip().lower()).strip("-") or "merge"
        merge_stdout = context.paths.logs_dir / f"{normalized_label}.stdout.log"
        merge_stderr = context.paths.logs_dir / f"{normalized_label}.stderr.log"
        summary = (
            f"{command} conflicted on "
            f"{', '.join(conflicted_files) or 'unknown files'}"
        )
        write_text(merge_stdout, str(getattr(merge_result, "stdout", "") or ""))
        write_text(
            merge_stderr,
            str(getattr(merge_result, "stderr", "") or "").strip()
            or summary,
        )
        return TestRunResult(
            command=command,
            returncode=getattr(merge_result, "returncode", 1) or 1,
            stdout_file=merge_stdout,
            stderr_file=merge_stderr,
            summary=summary,
            failure_reason=summary,
        )

    def _parallel_merge_conflict_test_result(
        self,
        *,
        context: ProjectContext,
        worker_commit: str,
        merge_result,
        conflicted_files: list[str],
    ) -> TestRunResult:
        return self._merge_conflict_test_result(
            context=context,
            label="parallel-batch-merge",
            command=f"git cherry-pick {worker_commit}",
            merge_result=merge_result,
            conflicted_files=conflicted_files,
        )

    def _report_failure(
        self,
        context: ProjectContext,
        reporter: Reporter,
        *,
        failure_type: str,
        summary: str,
        block_index: int | None = None,
        selected_task: str = "",
        extra: dict | None = None,
    ) -> None:
        reporter.write_status_report()
        bundle = reporter.write_failure_bundle(
            failure_type=failure_type,
            summary=summary,
            block_index=block_index,
            selected_task=selected_task,
            extra=extra,
        )
        post_result = reporter.post_pr_failure_report(bundle)
        write_json(
            context.paths.reports_dir / "latest_pr_failure_status.json",
            {
                "generated_at": now_utc_iso(),
                "failure_type": failure_type,
                "posted": bool(post_result.get("posted")),
                "result": post_result,
                "report_markdown_file": bundle.get("report_markdown_file", ""),
                "report_json_file": bundle.get("report_json_file", ""),
            },
        )

    def clear_latest_failure_status(self, context: ProjectContext) -> None:
        latest_failure_file = context.paths.reports_dir / "latest_pr_failure_status.json"
        try:
            latest_failure_file.unlink(missing_ok=True)
        except OSError:
            write_json(latest_failure_file, {})

    def _read_supplied_plan_text(self, plan_path: Path | None, plan_input: str) -> str:
        if plan_input.strip():
            return plan_input.strip()
        if plan_path:
            return read_text(Path(plan_path)).strip()
        return ""

    def _resolve_plan_text(
        self,
        context: ProjectContext,
        runtime: RuntimeOptions,
        repo_inputs: dict[str, str],
        is_mature: bool,
        maturity_details: dict[str, int],
        plan_path: Path | None,
        plan_input: str,
    ) -> str:
        supplied_text = self._read_supplied_plan_text(plan_path, plan_input)
        if supplied_text:
            if is_plan_markdown(supplied_text):
                return supplied_text
            return self._generate_plan_from_prompt(context, runtime, repo_inputs, supplied_text, maturity_details)
        if context.paths.plan_file.exists():
            return read_text(context.paths.plan_file)
        if is_mature:
            return generate_project_plan(context, repo_inputs)
        if runtime.init_plan_prompt.strip():
            return self._generate_plan_from_prompt(
                context,
                runtime,
                repo_inputs,
                runtime.init_plan_prompt,
                maturity_details,
            )
        return generate_project_plan(context, repo_inputs)

    def _generate_plan_from_prompt(
        self,
        context: ProjectContext,
        runtime: RuntimeOptions,
        repo_inputs: dict[str, str],
        user_prompt: str,
        maturity_details: dict[str, int],
    ) -> str:
        runner = CodexRunner(runtime.codex_path)
        planning_effort = self._resolved_planning_effort(runtime)
        prompt_started_at = perf_counter()
        prompt = bootstrap_plan_prompt(context, repo_inputs, user_prompt)
        self._log_planning_metric(
            context,
            "bootstrap_prompt_build",
            started_at=prompt_started_at,
            flow="planning-bootstrap",
        )
        agent_started_at = perf_counter()
        result = self._run_pass_with_provider_fallback(
            context=context,
            runner=runner,
            prompt=prompt,
            pass_type="init-project-plan",
            block_index=0,
            search_enabled=False,
            reasoning_effort=planning_effort,
        )
        self._log_planning_metric(
            context,
            "bootstrap_plan_agent",
            started_at=agent_started_at,
            flow="planning-bootstrap",
            details={"returncode": result.returncode},
        )
        plan_text = read_text(context.paths.plan_file)
        if result.returncode != 0 or not plan_text.strip():
            raise RuntimeError(
                f"Codex failed to create the initial prompt-based project plan. maturity={maturity_details}"
            )
        return plan_text

    def _write_planning_state(self, context: ProjectContext, runtime: RuntimeOptions, plan_text: str) -> None:
        write_text(context.paths.plan_file, plan_text)
        write_text(context.paths.scope_guard_file, ensure_scope_guard(context))
        mid_term_text, _ = build_mid_term_plan(plan_text)
        write_text(context.paths.mid_term_plan_file, mid_term_text)
        checkpoints = build_checkpoint_timeline(plan_text, runtime.checkpoint_interval_blocks)
        write_text(context.paths.checkpoint_timeline_file, checkpoint_timeline_markdown(checkpoints))
        write_json(context.paths.checkpoint_state_file, {"checkpoints": [checkpoint.to_dict() for checkpoint in checkpoints]})

    def _plan_block_items(
        self,
        context: ProjectContext,
        runner: CodexRunner,
        plan_text: str,
        work_items: list[str] | None,
        max_items: int,
        repo_inputs: dict[str, str] | None = None,
    ) -> tuple[list, str]:
        if work_items:
            remaining_items = work_items[max(0, context.loop_state.block_index - 1):]
            mid_term_text, mid_items = build_mid_term_plan_from_user_items(remaining_items or work_items)
            return mid_items, mid_term_text

        cache_lookup_started_at = perf_counter()
        cached_mid_term = self._load_cached_block_plan(
            context,
            plan_text=plan_text,
            max_items=max_items,
            repo_inputs=repo_inputs,
            work_items=work_items,
        )
        if cached_mid_term is not None:
            cached_items, cached_text = cached_mid_term
            valid_subset, violations = validate_mid_term_subset(cached_text, plan_text)
            self._log_planning_metric(
                context,
                "block_plan_cache_lookup",
                started_at=cache_lookup_started_at,
                flow="block-planning",
                details={"cache_hit": valid_subset, "item_count": len(cached_items)},
            )
            if valid_subset:
                return cached_items, cached_text
            write_text(context.paths.reports_dir / "plan_scope_violation.txt", "\n".join(violations) + "\n")
        else:
            self._log_planning_metric(
                context,
                "block_plan_cache_lookup",
                started_at=cache_lookup_started_at,
                flow="block-planning",
                details={"cache_hit": False},
            )

        planned_items = self._generate_codex_work_items(
            context=context,
            runner=runner,
            plan_text=plan_text,
            max_items=max_items,
            repo_inputs=repo_inputs,
        )
        if planned_items:
            generated_description = (
                "This plan was generated by Codex from the current repository state and saved project plan."
            )
            mid_term_text, mid_items = build_mid_term_plan_from_plan_items(
                planned_items,
                generated_description,
            )
            valid_subset, violations = validate_mid_term_subset(mid_term_text, plan_text)
            if valid_subset:
                self._store_block_plan_cache(
                    context,
                    plan_text=plan_text,
                    max_items=max_items,
                    repo_inputs=repo_inputs,
                    work_items=work_items,
                    mid_items=mid_items,
                    mid_term_text=mid_term_text,
                    description=generated_description,
                )
                return mid_items, mid_term_text
            write_text(context.paths.reports_dir / "plan_scope_violation.txt", "\n".join(violations) + "\n")

        mid_term_text, mid_items = build_mid_term_plan(plan_text)
        valid_subset, violations = validate_mid_term_subset(mid_term_text, plan_text)
        if not valid_subset:
            raise RuntimeError(f"Mid-term plan violated saved plan scope: {violations}")
        self._store_block_plan_cache(
            context,
            plan_text=plan_text,
            max_items=max_items,
            repo_inputs=repo_inputs,
            work_items=work_items,
            mid_items=mid_items,
            mid_term_text=mid_term_text,
            description="This plan is regenerated only at block boundaries and must remain a strict subset of the saved project plan.",
        )
        return mid_items, mid_term_text

    def _generate_codex_work_items(
        self,
        context: ProjectContext,
        runner: CodexRunner,
        plan_text: str,
        max_items: int,
        repo_inputs: dict[str, str] | None = None,
    ) -> list:
        planning_effort = self._resolved_planning_effort(context.runtime)
        if repo_inputs is None:
            repo_inputs_started_at = perf_counter()
            repo_inputs = self._scan_repository_inputs(context)
            self._log_planning_metric(
                context,
                "block_context_scan",
                started_at=repo_inputs_started_at,
                flow="block-planning",
            )
        prompt_started_at = perf_counter()
        memory_context = MemoryStore(context.paths).render_context(plan_text)
        prompt = work_breakdown_prompt(
            context=context,
            repo_inputs=repo_inputs,
            plan_text=plan_text,
            memory_context=memory_context,
            max_items=max_items,
        )
        self._log_planning_metric(
            context,
            "block_prompt_build",
            started_at=prompt_started_at,
            flow="block-planning",
            details={"max_items": max_items},
        )
        agent_started_at = perf_counter()
        result = self._run_pass_with_provider_fallback(
            context=context,
            runner=runner,
            prompt=prompt,
            pass_type="plan-work-breakdown",
            block_index=max(0, context.loop_state.block_index),
            search_enabled=False,
            reasoning_effort=planning_effort,
        )
        self._log_planning_metric(
            context,
            "block_agent_breakdown",
            started_at=agent_started_at,
            flow="block-planning",
            details={"returncode": result.returncode},
        )
        if result.returncode != 0:
            return []
        parse_started_at = perf_counter()
        items = parse_work_breakdown_response(result.last_message or "", limit=max_items)
        self._log_planning_metric(
            context,
            "block_breakdown_parse",
            started_at=parse_started_at,
            flow="block-planning",
            details={"item_count": len(items)},
        )
        return items
