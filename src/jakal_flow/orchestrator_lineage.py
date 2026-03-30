from __future__ import annotations

from collections.abc import Callable
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import shutil
from pathlib import Path
from uuid import uuid4

from .commit_naming import build_commit_descriptor, build_initial_commit_descriptor
from .contract_wave import (
    DEFAULT_SPINE_VERSION,
    PromotionAssessment,
    build_lineage_manifest,
    classify_completed_lineage_step,
    current_spine_version,
    load_lineage_manifests,
    manifest_symbol_inventory_paths,
    manifest_summary_markdown,
    normalize_execution_step_policy,
    persist_lineage_completion_artifacts,
    policy_summary,
)
from .environment import ensure_gitignore, ensure_virtualenv
from . import execution_plan_support
from .codex_runner import CodexRunner
from .errors import HANDLED_OPERATION_EXCEPTIONS, PromotionRollbackError
from .execution_control import ImmediateStopRequested
from .git_ops import GitCommandError, GitOps
from .memory import MemoryStore
from .model_providers import normalize_billing_mode, provider_preset, provider_supports_auto_model
from .provider_fallbacks import (
    build_provider_fallback_runtimes,
    is_provider_fallbackable_error,
    is_quota_exhaustion_error,
)
from .model_selection import normalize_reasoning_effort
from .models import CandidateTask, Checkpoint, CodexRunResult, ExecutionPlanState, ExecutionStep, LineageState, LoopState, MLExperimentRecord, MLModeState, ProjectContext, ProjectPaths, RepoMetadata, RuntimeOptions, TestRunResult
from .optimization import scan_optimization_candidates
from .parallel_resources import build_parallel_resource_plan, normalize_parallel_worker_mode
from .platform_defaults import default_codex_path
from .planning import (
    FINALIZATION_PROMPT_FILENAME,
    attempt_history_entry,
    assess_repository_maturity,
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
    execution_plan_svg,
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
from .status_views import status_from_plan_state
from .step_models import normalize_step_model, normalize_step_model_provider, provider_execution_preflight_error, resolve_step_model_choice
from .utils import compact_text, ensure_dir, normalize_workflow_mode, now_utc_iso, read_json, read_jsonl_tail, read_last_jsonl, read_text, remove_tree, svg_text_element, wrap_svg_text, write_json, write_text
from .verification import VerificationRunner
from .workspace import WorkspaceManager

UTC = getattr(datetime, "UTC", timezone.utc)


class OrchestratorLineageMixin:
    def _plan_uses_hybrid_lineages(self, plan_state: ExecutionPlanState) -> bool:
        return any(self._step_kind(step) in {"join", "barrier"} for step in plan_state.steps)
    def _load_lineage_states(self, context: ProjectContext) -> dict[str, LineageState]:
        payload = read_json(context.paths.lineage_state_file, default={"lineages": []})
        items = payload.get("lineages", []) if isinstance(payload, dict) else []
        lineages: dict[str, LineageState] = {}
        if not isinstance(items, list):
            return lineages
        for item in items:
            if not isinstance(item, dict):
                continue
            lineage = LineageState.from_dict(item)
            if lineage.lineage_id:
                lineages[lineage.lineage_id] = lineage
        return lineages
    def _save_lineage_states(self, context: ProjectContext, lineages: dict[str, LineageState]) -> None:
        write_json(
            context.paths.lineage_state_file,
            {
                "lineages": [
                    lineage.to_dict()
                    for lineage in sorted(
                        lineages.values(),
                        key=lambda item: (item.created_at, item.lineage_id),
                    )
                ]
            },
        )
    def _next_lineage_id(self, lineages: dict[str, LineageState]) -> str:
        next_index = 1
        for lineage_id in lineages:
            if lineage_id.startswith("LN") and lineage_id[2:].isdigit():
                next_index = max(next_index, int(lineage_id[2:]) + 1)
        while f"LN{next_index}" in lineages:
            next_index += 1
        return f"LN{next_index}"
    def _lineage_branch_name(self, lineage_id: str) -> str:
        return f"jakal-flow-lineage-{lineage_id.strip().lower()}-{uuid4().hex[:8]}"
    def _lineage_root(self, context: ProjectContext, lineage_id: str) -> Path:
        return context.paths.project_root / ".lineages" / lineage_id.strip().lower()
    def _build_lineage_paths(
        self,
        context: ProjectContext,
        lineage_id: str,
        worktree_dir: Path,
    ) -> ProjectPaths:
        lineage_root = self._lineage_root(context, lineage_id)
        docs_dir = lineage_root / "docs"
        memory_dir = lineage_root / "memory"
        legacy_logs_dir = lineage_root / "logs"
        logs_dir = WorkspaceManager.repo_logs_dir(worktree_dir)
        reports_dir = lineage_root / "reports"
        state_dir = lineage_root / "state"
        lineage_manifests_dir = state_dir / "lineage_manifests"
        for directory in [lineage_root, docs_dir, memory_dir, logs_dir, reports_dir, state_dir, lineage_manifests_dir]:
            ensure_dir(directory)
        self.workspace.migrate_logs_dir(legacy_logs_dir, logs_dir)
        return ProjectPaths(
            workspace_root=context.paths.workspace_root,
            projects_root=context.paths.projects_root,
            project_root=lineage_root,
            repo_dir=worktree_dir,
            docs_dir=docs_dir,
            memory_dir=memory_dir,
            logs_dir=logs_dir,
            reports_dir=reports_dir,
            state_dir=state_dir,
            metadata_file=lineage_root / "metadata.json",
            project_config_file=lineage_root / "project_config.json",
            loop_state_file=state_dir / "LOOP_STATE.json",
            plan_file=docs_dir / "PLAN.md",
            mid_term_plan_file=docs_dir / "MID_TERM_PLAN.md",
            scope_guard_file=docs_dir / "SCOPE_GUARD.md",
            active_task_file=docs_dir / "ACTIVE_TASK.md",
            block_review_file=docs_dir / "BLOCK_REVIEW.md",
            checkpoint_timeline_file=docs_dir / "CHECKPOINT_TIMELINE.md",
            research_notes_file=docs_dir / "RESEARCH_NOTES.md",
            attempt_history_file=docs_dir / "attempt_history.md",
            success_patterns_file=memory_dir / "success_patterns.jsonl",
            failure_patterns_file=memory_dir / "failure_patterns.jsonl",
            task_summaries_file=memory_dir / "task_summaries.jsonl",
            pass_log_file=logs_dir / "passes.jsonl",
            block_log_file=logs_dir / "blocks.jsonl",
            planning_metrics_file=logs_dir / "planning_metrics.jsonl",
            checkpoint_state_file=state_dir / "CHECKPOINTS.json",
            execution_plan_file=state_dir / "EXECUTION_PLAN.json",
            planning_inputs_cache_file=state_dir / "PLANNING_INPUTS_CACHE.json",
            planning_prompt_cache_file=state_dir / "PLANNING_PROMPT_CACHE.json",
            block_plan_cache_file=state_dir / "BLOCK_PLAN_CACHE.json",
            lineage_state_file=state_dir / "LINEAGES.json",
            spine_file=state_dir / "SPINE.json",
            common_requirements_file=state_dir / "COMMON_REQUIREMENTS.json",
            contract_wave_audit_file=state_dir / "CONTRACT_WAVE_AUDIT.jsonl",
            ml_mode_state_file=state_dir / "ML_MODE_STATE.json",
            ml_step_report_file=state_dir / "ML_STEP_REPORT.json",
            ml_experiment_reports_dir=state_dir / "ml_experiments",
            lineage_manifests_dir=lineage_manifests_dir,
            ui_control_file=state_dir / "UI_RUN_CONTROL.json",
            ui_event_log_file=logs_dir / "ui_events.jsonl",
            execution_flow_svg_file=docs_dir / "EXECUTION_FLOW.svg",
            closeout_report_file=docs_dir / "CLOSEOUT_REPORT.md",
            closeout_report_docx_file=reports_dir / "CLOSEOUT_REPORT.docx",
            closeout_report_pptx_file=reports_dir / "CLOSEOUT_REPORT.pptx",
            ml_experiment_report_file=docs_dir / "ML_EXPERIMENT_REPORT.md",
            ml_experiment_results_svg_file=docs_dir / "ML_EXPERIMENT_RESULTS.svg",
            shared_contracts_file=docs_dir / "SHARED_CONTRACTS.md",
        )
    def _sync_lineage_support_files(self, context: ProjectContext, lineage_paths: ProjectPaths) -> None:
        for source_dir, target_dir in [
            (context.paths.docs_dir, lineage_paths.docs_dir),
            (context.paths.memory_dir, lineage_paths.memory_dir),
        ]:
            ensure_dir(target_dir)
            if source_dir.exists():
                shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)
        for source_path, target_path in [
            (context.paths.spine_file, lineage_paths.spine_file),
            (context.paths.common_requirements_file, lineage_paths.common_requirements_file),
            (context.paths.ml_mode_state_file, lineage_paths.ml_mode_state_file),
            (context.paths.ui_control_file, lineage_paths.ui_control_file),
        ]:
            if not source_path.exists():
                continue
            ensure_dir(target_path.parent)
            shutil.copy2(source_path, target_path)
        if context.paths.lineage_manifests_dir.exists():
            ensure_dir(lineage_paths.lineage_manifests_dir)
            shutil.copytree(context.paths.lineage_manifests_dir, lineage_paths.lineage_manifests_dir, dirs_exist_ok=True)
    def _sanitize_child_execution_plan_state(self, plan_state: ExecutionPlanState) -> ExecutionPlanState:
        sanitized = deepcopy(plan_state)
        for step in sanitized.steps:
            if step.status == "completed":
                continue
            step.status = "pending"
            step.started_at = None
            step.completed_at = None
            step.commit_hash = None
            step.notes = ""
            self._clear_step_failure_metadata(step)
        if sanitized.closeout_status != "completed":
            sanitized.closeout_status = "not_started"
            sanitized.closeout_started_at = None
            sanitized.closeout_completed_at = None
            sanitized.closeout_commit_hash = None
            sanitized.closeout_notes = ""
        return sanitized
    def _sync_child_execution_plan_state(
        self,
        source_context: ProjectContext,
        child_context: ProjectContext,
    ) -> None:
        parent_plan_state = self.load_execution_plan_state(source_context)
        self.save_execution_plan_state(
            child_context,
            self._sanitize_child_execution_plan_state(parent_plan_state),
        )
    def _persist_context_files(self, context: ProjectContext) -> None:
        write_json(context.paths.metadata_file, context.metadata.to_dict())
        write_json(context.paths.project_config_file, context.runtime.to_dict())
        write_json(context.paths.loop_state_file, context.loop_state.to_dict())
    def _normal_task_child_counts(self, plan_state: ExecutionPlanState) -> dict[str, int]:
        counts: dict[str, int] = {}
        for step in plan_state.steps:
            if self._step_kind(step) != "task":
                continue
            for dependency in step.depends_on:
                counts[dependency] = counts.get(dependency, 0) + 1
        return counts
    def _create_lineage_state(
        self,
        context: ProjectContext,
        lineages: dict[str, LineageState],
        *,
        source_revision: str,
        parent_lineage_id: str | None = None,
        source_step_id: str | None = None,
    ) -> LineageState:
        lineage_id = self._next_lineage_id(lineages)
        lineage_root = self._lineage_root(context, lineage_id)
        worktree_dir = lineage_root / "repo"
        branch_name = self._lineage_branch_name(lineage_id)
        self.git.add_worktree(context.paths.repo_dir, worktree_dir, branch_name, source_revision)
        created_at = now_utc_iso()
        lineage = LineageState(
            lineage_id=lineage_id,
            branch_name=branch_name,
            worktree_dir=worktree_dir,
            project_root=lineage_root,
            created_at=created_at,
            updated_at=created_at,
            head_commit=source_revision,
            safe_revision=source_revision,
            status="active",
            parent_lineage_id=parent_lineage_id,
            source_step_id=source_step_id,
        )
        lineages[lineage_id] = lineage
        return lineage
    def _build_lineage_context(
        self,
        context: ProjectContext,
        runtime: RuntimeOptions,
        step: ExecutionStep,
        lineage: LineageState,
    ) -> ProjectContext:
        source_revision = lineage.head_commit or lineage.safe_revision or context.metadata.current_safe_revision or self.git.current_revision(
            context.paths.repo_dir
        )
        if not lineage.worktree_dir.exists():
            if self.git.branch_exists(context.paths.repo_dir, lineage.branch_name):
                self.git.attach_worktree(context.paths.repo_dir, lineage.worktree_dir, lineage.branch_name)
            else:
                self.git.add_worktree(context.paths.repo_dir, lineage.worktree_dir, lineage.branch_name, source_revision)
        lineage_paths = self._build_lineage_paths(context, lineage.lineage_id, lineage.worktree_dir)
        self._sync_lineage_support_files(context, lineage_paths)
        lineage_runtime = self._build_parallel_worker_runtime(runtime, step)
        lineage_metadata = RepoMetadata(
            repo_id=f"{context.metadata.repo_id}:{lineage.lineage_id.lower()}",
            slug=f"{context.metadata.slug}-{lineage.lineage_id.lower()}",
            repo_url=context.metadata.repo_url,
            branch=lineage.branch_name,
            project_root=lineage_paths.project_root,
            repo_path=lineage.worktree_dir,
            created_at=lineage.created_at,
            last_run_at=lineage.updated_at,
            current_status="lineage_ready",
            current_safe_revision=lineage.safe_revision or source_revision,
            repo_kind=context.metadata.repo_kind,
            display_name=f"{context.metadata.display_name or context.metadata.slug} [{lineage.lineage_id}]",
            origin_url=context.metadata.origin_url,
            source_repo_id=context.metadata.source_repo_id or context.metadata.repo_id,
        )
        lineage_loop_state = LoopState(
            repo_id=lineage_metadata.repo_id,
            repo_slug=lineage_metadata.slug,
            current_safe_revision=lineage.safe_revision or source_revision,
        )
        lineage_context = ProjectContext(
            metadata=lineage_metadata,
            runtime=lineage_runtime,
            paths=lineage_paths,
            loop_state=lineage_loop_state,
        )
        self._sync_child_execution_plan_state(context, lineage_context)
        self._ensure_project_documents(lineage_context)
        self._persist_context_files(lineage_context)
        return lineage_context
    def _allocate_lineage_for_step(
        self,
        context: ProjectContext,
        plan_state: ExecutionPlanState,
        step: ExecutionStep,
        lineages: dict[str, LineageState],
        child_counts: dict[str, int],
    ) -> LineageState:
        metadata = deepcopy(step.metadata) if isinstance(step.metadata, dict) else {}
        existing_lineage_id = str(metadata.get("lineage_id", "")).strip()
        if existing_lineage_id and existing_lineage_id in lineages:
            return lineages[existing_lineage_id]

        step_by_id = {item.step_id: item for item in plan_state.steps}
        dependencies = [step_by_id[dependency] for dependency in step.depends_on if dependency in step_by_id]
        main_safe_revision = context.metadata.current_safe_revision or self.git.current_revision(context.paths.repo_dir)
        if not dependencies:
            lineage = self._create_lineage_state(context, lineages, source_revision=main_safe_revision)
        elif len(dependencies) > 1:
            raise RuntimeError(f"{step.step_id} requires an explicit join or barrier before continuing from multiple dependencies.")
        else:
            parent_step = dependencies[0]
            if self._step_kind(parent_step) in {"join", "barrier"}:
                lineage = self._create_lineage_state(
                    context,
                    lineages,
                    source_revision=main_safe_revision,
                    source_step_id=parent_step.step_id,
                )
            else:
                parent_lineage_id = str((parent_step.metadata or {}).get("lineage_id", "")).strip()
                if not parent_lineage_id or parent_lineage_id not in lineages:
                    raise RuntimeError(f"{step.step_id} depends on {parent_step.step_id}, but that lineage is unavailable.")
                parent_lineage = lineages[parent_lineage_id]
                parent_head = parent_lineage.head_commit or parent_lineage.safe_revision
                if child_counts.get(parent_step.step_id, 0) > 1:
                    parent_lineage.status = "branched"
                    parent_lineage.updated_at = now_utc_iso()
                    lineage = self._create_lineage_state(
                        context,
                        lineages,
                        source_revision=parent_head,
                        parent_lineage_id=parent_lineage.lineage_id,
                        source_step_id=parent_step.step_id,
                    )
                else:
                    lineage = parent_lineage
        metadata["lineage_id"] = lineage.lineage_id
        step.metadata = metadata
        return lineage
    def _run_lineage_step_worker(
        self,
        lineage_context: ProjectContext,
        step: ExecutionStep,
    ) -> dict[str, object]:
        lineage_result: dict[str, object] = {
            "step_id": step.step_id,
            "status": "failed",
            "notes": "Lineage worker did not complete.",
            "commit_hash": None,
            "changed_files": [],
            "pass_log": {},
            "block_log": {},
            "test_summary": "",
            "ml_report_payload": {},
            "head_commit": lineage_context.metadata.current_safe_revision,
        }
        try:
            candidate = CandidateTask(
                candidate_id=step.step_id,
                title=step.title,
                rationale=self._execution_step_rationale(step, lineage_context.runtime.test_cmd),
                plan_refs=[step.step_id],
                score=1.0,
            )
            runner = CodexRunner(lineage_context.runtime.codex_path)
            memory = MemoryStore(lineage_context.paths)
            reporter = Reporter(lineage_context)
            latest_block, _attempt_count = self._run_execution_step_attempts(
                context=lineage_context,
                runner=runner,
                memory=memory,
                reporter=reporter,
                candidate=candidate,
                execution_step=deepcopy(step),
                final_failure_reports=False,
            )
            latest_block = latest_block or {}
            latest_pass = read_last_jsonl(lineage_context.paths.pass_log_file) or {}
            changed_files = latest_block.get("changed_files", latest_pass.get("changed_files", []))
            commit_hashes = latest_block.get("commit_hashes", [])
            commit_hash = None
            if isinstance(commit_hashes, list) and commit_hashes:
                commit_hash = str(commit_hashes[-1]).strip() or None
            head_commit = (
                str(lineage_context.metadata.current_safe_revision or "").strip()
                or (self.git.current_revision(lineage_context.paths.repo_dir) if lineage_context.paths.repo_dir.exists() else "")
            )
            lineage_result.update(
                {
                    "status": "completed" if latest_block.get("status") == "completed" else "failed",
                    "notes": str(latest_block.get("test_summary") or "").strip() or "Lineage worker finished.",
                    "commit_hash": commit_hash,
                    "changed_files": [str(item).strip() for item in changed_files if str(item).strip()] if isinstance(changed_files, list) else [],
                    "pass_log": latest_pass,
                    "block_log": latest_block,
                    "test_summary": str(latest_block.get("test_summary") or "").strip(),
                    "ml_report_payload": read_json(lineage_context.paths.ml_step_report_file, default={}),
                    "head_commit": head_commit,
                }
            )
        except ImmediateStopRequested as exc:
            lineage_result["status"] = "paused"
            lineage_result["notes"] = str(exc).strip() or "Immediate stop requested."
        except HANDLED_OPERATION_EXCEPTIONS as exc:
            lineage_result["status"] = "failed"
            lineage_result["notes"] = str(exc).strip() or "Lineage worker failed."
        finally:
            self._persist_context_files(lineage_context)
        return lineage_result
    def _lineage_worker_failure_result(
        self,
        *,
        context: ProjectContext,
        lineages: dict[str, LineageState],
        step: ExecutionStep,
        error: Exception | str,
    ) -> dict[str, object]:
        lineage_id = str((step.metadata or {}).get("lineage_id", "")).strip()
        lineage = lineages.get(lineage_id)
        note = str(error).strip() or "Lineage worker failed."
        head_commit = ""
        if lineage is not None:
            head_commit = str(lineage.head_commit or lineage.safe_revision or "").strip()
        if not head_commit:
            head_commit = str(context.metadata.current_safe_revision or "").strip()
        return {
            "step_id": step.step_id,
            "status": "failed",
            "notes": note,
            "commit_hash": None,
            "changed_files": [],
            "pass_log": {},
            "block_log": {},
            "test_summary": "",
            "ml_report_payload": {},
            "head_commit": head_commit,
        }
    def _cleanup_lineage_worktree(self, repo_dir: Path, lineage: LineageState) -> None:
        self.git.remove_worktree(repo_dir, lineage.worktree_dir, force=True)
        if lineage.branch_name:
            self.git.delete_branch(repo_dir, lineage.branch_name, force=True)
    def _evaluate_push_readiness(
        self,
        context: ProjectContext,
        repo_dir: Path,
        branch: str,
        commit_hash: str = "",
    ) -> tuple[bool, str]:
        target_branch = branch.strip()
        target_commit = commit_hash.strip()
        if not context.runtime.allow_push:
            return False, "push_disabled"
        if not repo_dir.exists():
            return False, "missing_repo_dir"
        if not target_branch:
            return False, "missing_branch"
        remote_url = self.git.remote_url(repo_dir, "origin")
        if not remote_url:
            return False, "missing_remote"
        local_head_result = self.git.run(["rev-parse", "--verify", target_branch], cwd=repo_dir, check=False)
        if local_head_result.returncode != 0:
            return False, "missing_local_branch"
        local_head = local_head_result.stdout.strip()
        if not local_head:
            return False, "missing_local_head"
        if target_commit:
            commit_result = self.git.run(["rev-parse", "--verify", target_commit], cwd=repo_dir, check=False)
            if commit_result.returncode != 0:
                return False, "missing_commit"
            if not self.git.is_ancestor(repo_dir, target_commit, local_head):
                return False, "commit_not_on_branch"
        remote_head = self.git.remote_branch_revision(repo_dir, "origin", target_branch)
        if remote_head and remote_head == local_head:
            return False, "already_up_to_date"
        if remote_head and not self.git.is_ancestor(repo_dir, remote_head, local_head):
            return False, "non_fast_forward"
        return True, "push_ready"
    def _push_if_ready(
        self,
        context: ProjectContext,
        repo_dir: Path,
        branch: str,
        commit_hash: str = "",
    ) -> tuple[bool, str]:
        ready, reason = self._evaluate_push_readiness(context, repo_dir, branch, commit_hash=commit_hash)
        if not ready:
            return False, reason
        try:
            self.git.push(repo_dir, branch)
            return True, "pushed"
        except GitCommandError as exc:
            detail = str(exc).strip().splitlines()[0] if str(exc).strip() else "unknown_error"
            return False, f"push_failed:{detail}"
    def _delete_remote_branch_if_present(
        self,
        context: ProjectContext,
        repo_dir: Path,
        branch: str,
        remote_name: str = "origin",
    ) -> tuple[bool, str]:
        target_branch = branch.strip()
        if not context.runtime.allow_push:
            return False, "push_disabled"
        if not repo_dir.exists():
            return False, "missing_repo_dir"
        if not target_branch:
            return False, "missing_branch"
        remote_url = self.git.remote_url(repo_dir, remote_name)
        if not remote_url:
            return False, "missing_remote"
        remote_head = self.git.remote_branch_revision(repo_dir, remote_name, target_branch)
        if not remote_head:
            return False, "missing_remote_branch"
        try:
            self.git.delete_remote_branch(repo_dir, remote_name, target_branch)
            return True, "deleted"
        except GitCommandError as exc:
            detail = str(exc).strip().splitlines()[0] if str(exc).strip() else "unknown_error"
            return False, f"delete_failed:{detail}"
    def _rollback_failed_promotion(
        self,
        context: ProjectContext,
        safe_revision: str,
        *,
        failure_detail: str,
    ) -> None:
        target_revision = str(safe_revision or "").strip()
        try:
            self.git.hard_reset(context.paths.repo_dir, target_revision)
        except GitCommandError as exc:
            rollback_detail = str(exc).strip().splitlines()[0] if str(exc).strip() else "unknown_error"
            raise PromotionRollbackError(
                f"Failed to restore safe revision {target_revision or 'unknown'} after promotion failure ({failure_detail or 'unknown_error'}): {rollback_detail}"
            ) from exc
        context.metadata.current_safe_revision = target_revision
        context.loop_state.current_safe_revision = target_revision
        context.loop_state.last_commit_hash = target_revision
    def _can_auto_promote_lineage_step(
        self,
        step: ExecutionStep,
        child_counts: dict[str, int],
        *,
        batch_size: int,
        assessment: PromotionAssessment | None = None,
    ) -> bool:
        if assessment is not None:
            return bool(assessment.auto_promote_eligible)
        return batch_size == 1 and self._step_kind(step) == "task" and child_counts.get(step.step_id, 0) == 0
    def _promote_lineage_to_target_branch(
        self,
        context: ProjectContext,
        lineage: LineageState,
    ) -> tuple[bool, str, str | None]:
        base_safe_revision = str(
            context.metadata.current_safe_revision
            or context.loop_state.current_safe_revision
            or self.git.current_revision(context.paths.repo_dir)
        ).strip()
        branch_name = str(lineage.branch_name or "").strip()
        if not branch_name:
            return False, "missing_lineage_branch", None
        try:
            self.git.merge_ff_only(context.paths.repo_dir, branch_name)
            integrated_revision = self.git.current_revision(context.paths.repo_dir)
        except GitCommandError as exc:
            detail = str(exc).strip().splitlines()[0] if str(exc).strip() else "unknown_error"
            self._rollback_failed_promotion(
                context,
                base_safe_revision,
                failure_detail=f"merge_failed:{detail}",
            )
            return False, f"merge_failed:{detail}", None

        context.metadata.current_safe_revision = integrated_revision
        context.loop_state.current_safe_revision = integrated_revision
        context.loop_state.last_commit_hash = integrated_revision
        pushed, push_reason = self._push_if_ready(
            context,
            context.paths.repo_dir,
            context.metadata.branch,
            commit_hash=integrated_revision,
        )
        if pushed or push_reason == "already_up_to_date":
            return True, push_reason, integrated_revision

        self._rollback_failed_promotion(
            context,
            base_safe_revision,
            failure_detail=push_reason,
        )
        return False, push_reason, None
    def _run_lineage_execution_batch(
        self,
        context: ProjectContext,
        plan_state: ExecutionPlanState,
        runtime: RuntimeOptions,
        ordered_targets: list[ExecutionStep],
    ) -> tuple[ProjectContext, ExecutionPlanState, list[ExecutionStep]]:
        if not ordered_targets:
            raise RuntimeError("No hybrid lineage steps were selected for execution.")
        if any(self._step_kind(step) != "task" for step in ordered_targets):
            raise RuntimeError("Hybrid lineage batches can only run normal task steps.")

        batch_label = ", ".join(step.step_id for step in ordered_targets)
        batch_started_at = now_utc_iso()
        requested = {step.step_id for step in ordered_targets}
        lineages = self._load_lineage_states(context)
        child_counts = self._normal_task_child_counts(plan_state)

        for step in plan_state.steps:
            if step.step_id in requested:
                step.status = "running"
                step.started_at = step.started_at or batch_started_at
                step.notes = ""
                self._allocate_lineage_for_step(context, plan_state, step, lineages, child_counts)
            elif step.status == "running":
                step.status = "paused"

        plan_state.default_test_command = runtime.test_cmd
        plan_state.execution_mode = "parallel"
        plan_state = self.save_execution_plan_state(context, plan_state)
        self._save_lineage_states(context, lineages)
        refreshed_targets = {step.step_id: step for step in plan_state.steps}
        ordered_targets = [refreshed_targets[step.step_id] for step in ordered_targets]
        lineages = self._load_lineage_states(context)

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
        context.metadata.current_status = "running:lineages"
        context.metadata.last_run_at = batch_started_at
        resolved_worker_count = max(1, self._parallel_worker_count(context.runtime))
        context.loop_state.current_task = f"Lineage batch {batch_label} (workers {resolved_worker_count})"
        self.save_execution_plan_state(context, plan_state)
        self.workspace.save_project(context)

        reporter = Reporter(context)
        worker_results: list[dict[str, object]] = []
        batch_manifests = []
        final_status = "completed"
        batch_summary = ""

        try:
            worker_contexts: dict[str, ProjectContext] = {}
            worker_results_by_step: dict[str, dict[str, object]] = {}
            for step in ordered_targets:
                lineage_id = str((step.metadata or {}).get("lineage_id", "")).strip()
                lineage = lineages.get(lineage_id)
                if lineage is None:
                    result = self._lineage_worker_failure_result(
                        context=context,
                        lineages=lineages,
                        step=step,
                        error=RuntimeError(f"{step.step_id} could not resolve an active lineage."),
                    )
                    worker_results_by_step[step.step_id] = result
                    plan_state, ordered_targets = self._sync_parallel_batch_step_progress(
                        context=context,
                        plan_state=plan_state,
                        ordered_targets=ordered_targets,
                        step_id=step.step_id,
                        worker_result=result,
                        success_status="completed",
                        running_status="running:lineages",
                    )
                    continue
                try:
                    worker_contexts[step.step_id] = self._build_lineage_context(context, runtime, step, lineage)
                except HANDLED_OPERATION_EXCEPTIONS as exc:
                    result = self._lineage_worker_failure_result(
                        context=context,
                        lineages=lineages,
                        step=step,
                        error=exc,
                    )
                    worker_results_by_step[step.step_id] = result
                    plan_state, ordered_targets = self._sync_parallel_batch_step_progress(
                        context=context,
                        plan_state=plan_state,
                        ordered_targets=ordered_targets,
                        step_id=step.step_id,
                        worker_result=result,
                        success_status="completed",
                        running_status="running:lineages",
                    )

            runnable_targets = [step for step in ordered_targets if step.step_id not in worker_results_by_step]
            worker_limit = max(1, min(len(runnable_targets), self._parallel_worker_count(context.runtime))) if runnable_targets else 0
            if worker_limit == 1:
                for step in runnable_targets:
                    try:
                        result = self._run_lineage_step_worker(worker_contexts[step.step_id], step)
                    except HANDLED_OPERATION_EXCEPTIONS as exc:
                        result = self._lineage_worker_failure_result(
                            context=context,
                            lineages=lineages,
                            step=step,
                            error=exc,
                        )
                    worker_results_by_step[step.step_id] = result
                    plan_state, ordered_targets = self._sync_parallel_batch_step_progress(
                        context=context,
                        plan_state=plan_state,
                        ordered_targets=ordered_targets,
                        step_id=step.step_id,
                        worker_result=result,
                        success_status="completed",
                        running_status="running:lineages",
                    )
            elif worker_limit > 1:
                with ThreadPoolExecutor(max_workers=worker_limit) as executor:
                    ordered_targets_by_id = {step.step_id: step for step in ordered_targets}
                    future_map = {
                        executor.submit(
                            self._run_lineage_step_worker,
                            worker_contexts[step.step_id],
                            step,
                        ): step.step_id
                        for step in runnable_targets
                    }
                    for future in as_completed(future_map):
                        result_step_id = str(future_map[future]).strip()
                        step = ordered_targets_by_id.get(result_step_id)
                        if step is None:
                            continue
                        try:
                            result = future.result()
                        except HANDLED_OPERATION_EXCEPTIONS as exc:
                            result = self._lineage_worker_failure_result(
                                context=context,
                                lineages=lineages,
                                step=step,
                                error=exc,
                            )
                        worker_results_by_step[result_step_id] = result
                        plan_state, ordered_targets = self._sync_parallel_batch_step_progress(
                            context=context,
                            plan_state=plan_state,
                            ordered_targets=ordered_targets,
                            step_id=result_step_id,
                            worker_result=result,
                            success_status="completed",
                            running_status="running:lineages",
                        )
                        ordered_targets_by_id = {item.step_id: item for item in ordered_targets}
            worker_results = [
                worker_results_by_step.get(step.step_id)
                or self._lineage_worker_failure_result(
                    context=context,
                    lineages=lineages,
                    step=step,
                    error=RuntimeError(f"{step.step_id} did not produce a worker result."),
                )
                for step in ordered_targets
            ]

            paused_worker = next((item for item in worker_results if str(item.get("status") or "").strip() == "paused"), None)
            if paused_worker is not None:
                final_status = "paused"
                batch_summary = str(paused_worker.get("notes") or "Immediate stop requested.").strip()
                for step in ordered_targets:
                    lineage_id = str((step.metadata or {}).get("lineage_id", "")).strip()
                    lineage = lineages.get(lineage_id)
                    if lineage is not None and lineage.worktree_dir.exists() and lineage.safe_revision:
                        self.git.hard_reset(lineage.worktree_dir, lineage.safe_revision)
                        lineage.status = "active"
                        lineage.notes = batch_summary
                        lineage.updated_at = now_utc_iso()
                    step.status = "paused"
                    step.completed_at = None
                    step.commit_hash = None
                    step.notes = batch_summary
                context.metadata.current_status = self._status_from_plan_state(plan_state)
            completion_time = now_utc_iso()
            batch_spine_version = current_spine_version(context.paths)
            for index, step in enumerate(ordered_targets):
                worker_result = worker_results[index] if index < len(worker_results) else {}
                lineage_id = str((step.metadata or {}).get("lineage_id", "")).strip()
                lineage = lineages.get(lineage_id)
                if lineage is None:
                    raise RuntimeError(f"{step.step_id} lost its lineage state during execution.")

                lineage.updated_at = completion_time
                lineage.last_step_id = step.step_id
                if step.step_id not in lineage.step_ids:
                    lineage.step_ids.append(step.step_id)

                if final_status == "paused":
                    continue
                if str(worker_result.get("status") or "").strip() == "completed":
                    normalize_execution_step_policy(
                        step,
                        step_kind=self._step_kind(step),
                        current_spine_version=batch_spine_version,
                    )
                    previous_safe_revision = str(lineage.safe_revision or lineage.head_commit or "").strip()
                    head_commit = str(
                        worker_result.get("head_commit")
                        or worker_result.get("commit_hash")
                        or lineage.head_commit
                        or lineage.safe_revision
                        or ""
                    ).strip()
                    if head_commit:
                        lineage.head_commit = head_commit
                        lineage.safe_revision = head_commit
                    lineage.status = "active"
                    lineage.notes = str(worker_result.get("test_summary") or worker_result.get("notes") or "").strip()

                    changed_files = sorted(set(str(item).strip() for item in worker_result.get("changed_files", []) if str(item).strip()))
                    assessment = classify_completed_lineage_step(
                        step,
                        changed_files=changed_files,
                        verification_passed=True,
                        batch_size=len(ordered_targets),
                        child_count=child_counts.get(step.step_id, 0),
                        step_kind=self._step_kind(step),
                    )
                    worker_result["promotion_assessment"] = assessment.to_dict()
                    step.promotion_class = assessment.promotion_class
                    diff_entries: list[tuple[str, str]] = []
                    previous_file_texts: dict[str, str] = {}
                    if previous_safe_revision and head_commit and previous_safe_revision != head_commit and lineage.worktree_dir.exists():
                        diff_entries = self.git.diff_name_status(lineage.worktree_dir, previous_safe_revision, head_commit)
                        for normalized_path in manifest_symbol_inventory_paths(changed_files, diff_entries):
                            previous_text = self.git.read_file_at_revision(
                                lineage.worktree_dir,
                                previous_safe_revision,
                                normalized_path,
                            )
                            if previous_text is not None:
                                previous_file_texts[normalized_path] = previous_text
                    manifest = build_lineage_manifest(
                        lineage_id=lineage.lineage_id,
                        step=step,
                        changed_files=changed_files,
                        diff_entries=diff_entries,
                        repo_dir=lineage.worktree_dir,
                        previous_file_texts=previous_file_texts,
                        verification_command=step.test_command or context.runtime.test_cmd,
                        verification_summary=str(worker_result.get("test_summary") or worker_result.get("notes") or "").strip(),
                        verification_passed=True,
                        assessment=assessment,
                        commit_hash=head_commit or str(worker_result.get("commit_hash") or "").strip(),
                    )
                    _spine_state, _requirements_state, crr_record, manifest_path = persist_lineage_completion_artifacts(
                        context.paths,
                        step=step,
                        lineage_id=lineage.lineage_id,
                        manifest=manifest,
                        assessment=assessment,
                    )
                    batch_spine_version = manifest.spine_version or _spine_state.current_version or batch_spine_version
                    normalize_execution_step_policy(
                        step,
                        step_kind=self._step_kind(step),
                        current_spine_version=batch_spine_version,
                    )
                    worker_result["lineage_manifest"] = manifest.to_dict()
                    worker_result["lineage_manifest_file"] = str(manifest_path)
                    batch_manifests.append(manifest)
                    lineage.latest_promotion_class = assessment.promotion_class
                    lineage.latest_spine_version = manifest.spine_version
                    if str(manifest_path) not in lineage.manifest_files:
                        lineage.manifest_files.append(str(manifest_path))
                    if crr_record is not None:
                        lineage.notes = (lineage.notes + f" | Common requirement request: {crr_record.request_id}").strip(" |")

                    promotion_result = {"promoted": False, "reason": "not_applicable", "commit_hash": None}
                    if self._can_auto_promote_lineage_step(
                        step,
                        child_counts,
                        batch_size=len(ordered_targets),
                        assessment=assessment,
                    ):
                        promoted, promotion_reason, integrated_revision = self._promote_lineage_to_target_branch(context, lineage)
                        promotion_result = {
                            "promoted": promoted,
                            "reason": promotion_reason,
                            "commit_hash": integrated_revision,
                        }
                        if promoted:
                            lineage.status = "merged"
                            lineage.merged_by_step_id = step.step_id
                            lineage.updated_at = completion_time
                            if integrated_revision:
                                lineage.head_commit = integrated_revision
                                lineage.safe_revision = integrated_revision
                            lineage.notes = (
                                lineage.notes + f" | Merged into `{context.metadata.branch}` immediately."
                            ).strip(" |")
                            worker_result["lineage_promotion"] = promotion_result
                            self._cleanup_lineage_worktree(context.paths.repo_dir, lineage)
                            step.status = "completed"
                            step.completed_at = completion_time
                            step.commit_hash = integrated_revision or (lineage.head_commit or None)
                            step.notes = lineage.notes or "Lineage step completed successfully."
                            continue
                        if promotion_reason not in {"not_applicable"}:
                            lineage.notes = (lineage.notes + f" | Immediate merge skipped: {promotion_reason}").strip(" |")
                    worker_result["lineage_promotion"] = promotion_result

                    push_result = {"pushed": False, "reason": "missing_head_commit"}
                    if lineage.head_commit:
                        pushed, push_reason = self._push_if_ready(
                            context,
                            lineage.worktree_dir,
                            lineage.branch_name,
                            commit_hash=lineage.head_commit,
                        )
                        push_result = {"pushed": pushed, "reason": push_reason}
                    worker_result["lineage_push"] = push_result
                    if push_result["pushed"]:
                        lineage.notes = (lineage.notes + " | Pushed lineage branch to origin.").strip(" |")
                        pr_result = self._maybe_open_pull_request(
                            context,
                            head_branch=lineage.branch_name,
                            base_branch=context.metadata.branch,
                            title=f"[{step.step_id}] {step.title}",
                            body=(
                                f"Automatically opened by jakal-flow for lineage `{lineage.lineage_id}`.\n\n"
                                f"- Step: `{step.step_id}`\n"
                                f"- Base branch: `{context.metadata.branch}`\n"
                                f"- Head branch: `{lineage.branch_name}`\n"
                            ),
                            status_filename=f"latest_pull_request_status_{lineage.lineage_id.lower()}.json",
                        )
                        worker_result["lineage_pull_request"] = pr_result
                        pr_url = str(pr_result.get("html_url") or "").strip()
                        if pr_url:
                            lineage.notes = (lineage.notes + f" | Pull request: {pr_url}").strip(" |")

                    step.status = "completed"
                    step.completed_at = completion_time
                    step.commit_hash = str(worker_result.get("commit_hash") or "").strip() or (lineage.head_commit or None)
                    step.notes = lineage.notes or "Lineage step completed successfully."
                else:
                    final_status = "failed"
                    failure_notes = str(worker_result.get("notes") or "Lineage step failed.").strip()
                    if not batch_summary:
                        batch_summary = failure_notes
                    lineage.status = "failed"
                    lineage.notes = failure_notes
                    step.status = "failed"
                    step.commit_hash = None
                    step.notes = failure_notes

            if final_status == "completed":
                batch_summary = "Lineage batch completed successfully."
                context.metadata.current_status = self._status_from_plan_state(plan_state)
            elif final_status == "failed":
                context.metadata.current_status = "failed"

            self._save_lineage_states(context, lineages)

            next_block_index = context.loop_state.block_index
            combined_changed_files: list[str] = []
            for index, step in enumerate(ordered_targets):
                next_block_index += 1
                worker_result = worker_results[index] if index < len(worker_results) else {}
                pass_entry = deepcopy(worker_result.get("pass_log") or {})
                block_entry = deepcopy(worker_result.get("block_log") or {})
                changed_files = sorted(set(str(item) for item in worker_result.get("changed_files", []) if str(item).strip()))
                combined_changed_files.extend(changed_files)
                rollback_status = "not_needed" if step.status == "completed" else "lineage_rolled_back_to_safe_revision"
                pass_entry.update(
                    {
                        "repository_id": context.metadata.repo_id,
                        "repository_slug": context.metadata.slug,
                        "block_index": next_block_index,
                        "selected_task": step.title,
                        "commit_hash": step.commit_hash if step.status == "completed" else None,
                        "rollback_status": rollback_status,
                        "changed_files": changed_files,
                        "test_results": pass_entry.get("test_results"),
                        "lineage_push": worker_result.get("lineage_push"),
                        "promotion_class": str(worker_result.get("promotion_assessment", {}).get("promotion_class", "")),
                        "promotion_assessment": worker_result.get("promotion_assessment"),
                        "lineage_manifest_file": worker_result.get("lineage_manifest_file"),
                    }
                )
                block_entry.update(
                    {
                        "repository_id": context.metadata.repo_id,
                        "repository_slug": context.metadata.slug,
                        "block_index": next_block_index,
                        "status": "completed" if step.status == "completed" else ("paused" if step.status == "paused" else "failed"),
                        "selected_task": step.title,
                        "changed_files": changed_files,
                        "test_summary": step.notes or batch_summary,
                        "commit_hashes": [step.commit_hash] if step.commit_hash else [],
                        "rollback_status": rollback_status,
                        "lineage_push": worker_result.get("lineage_push"),
                        "promotion_class": str(worker_result.get("promotion_assessment", {}).get("promotion_class", "")),
                        "promotion_assessment": worker_result.get("promotion_assessment"),
                        "lineage_manifest_file": worker_result.get("lineage_manifest_file"),
                    }
                )
                reporter.log_pass(pass_entry)
                reporter.log_block(block_entry)
                reporter.append_attempt_history(
                    attempt_history_entry(
                        next_block_index,
                        step.title,
                        "completed" if step.status == "completed" else ("lineage step paused" if step.status == "paused" else "lineage step failed"),
                        [step.commit_hash] if step.commit_hash else [],
                    )
                )
                self._collect_ml_step_report(
                    context,
                    step,
                    report_payload=worker_result.get("ml_report_payload") if isinstance(worker_result.get("ml_report_payload"), dict) else {},
                )

            context.loop_state.block_index = next_block_index
            context.loop_state.last_block_completed_at = completion_time
            block_review = reflection_markdown(
                f"Lineage batch {batch_label}",
                batch_summary or "Lineage batch finished.",
                sorted(set(combined_changed_files)),
                [step.commit_hash for step in ordered_targets if step.commit_hash],
            )
            if batch_manifests:
                block_review = f"{block_review.rstrip()}\n\n{manifest_summary_markdown(batch_manifests)}\n"
            reporter.write_block_review(block_review)
            if final_status == "failed":
                self._report_failure(
                    context,
                    reporter,
                    failure_type="lineage_batch_failed",
                    summary=batch_summary or "Lineage batch failed.",
                    block_index=context.loop_state.block_index,
                    selected_task=f"Lineage batch {batch_label}",
                )
            saved = self.save_execution_plan_state(context, plan_state)
            return context, saved, ordered_targets
        finally:
            context.runtime = previous_runtime
            context.metadata.last_run_at = now_utc_iso()
            self.workspace.save_project(context)
    def _lineages_for_join_step(
        self,
        plan_state: ExecutionPlanState,
        step: ExecutionStep,
        lineages: dict[str, LineageState],
    ) -> list[LineageState]:
        metadata = step.metadata if isinstance(step.metadata, dict) else {}
        merge_refs = self._coerce_string_list(metadata.get("merge_from", [])) or list(step.depends_on)
        step_by_id = {item.step_id: item for item in plan_state.steps}
        selected: list[LineageState] = []
        seen_lineages: set[str] = set()
        for ref in merge_refs:
            source_step = step_by_id.get(ref)
            if source_step is None:
                raise RuntimeError(f"{step.step_id} references unknown upstream step {ref}.")
            lineage_id = str((source_step.metadata or {}).get("lineage_id", "")).strip()
            if not lineage_id:
                continue
            if lineage_id in seen_lineages:
                continue
            lineage = lineages.get(lineage_id)
            if lineage is None:
                raise RuntimeError(f"{step.step_id} references lineage {lineage_id}, but that lineage is unavailable.")
            if str(lineage.status or "").strip().lower() == "merged":
                continue
            seen_lineages.add(lineage_id)
            selected.append(lineage)
        return selected
    def _integration_token(self, step: ExecutionStep) -> str:
        raw = f"{step.step_id.strip().lower() or 'join'}-{uuid4().hex[:8]}"
        return "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in raw).strip("-") or uuid4().hex[:8]
    def _integration_root(self, context: ProjectContext, integration_token: str) -> Path:
        return context.paths.project_root / ".integrations" / integration_token
    def _integration_branch_name(self, step: ExecutionStep, integration_token: str) -> str:
        step_slug = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in step.step_id.strip().lower()).strip("-") or "join"
        token_slug = integration_token.strip().lower()[-8:] or uuid4().hex[:8]
        return f"jakal-flow-integration-{step_slug}-{token_slug}"
    def _build_integration_paths(
        self,
        context: ProjectContext,
        integration_token: str,
        worktree_dir: Path,
    ) -> ProjectPaths:
        integration_root = self._integration_root(context, integration_token)
        docs_dir = integration_root / "docs"
        memory_dir = integration_root / "memory"
        legacy_logs_dir = integration_root / "logs"
        logs_dir = WorkspaceManager.repo_logs_dir(worktree_dir)
        reports_dir = integration_root / "reports"
        state_dir = integration_root / "state"
        lineage_manifests_dir = state_dir / "lineage_manifests"
        for directory in [integration_root, docs_dir, memory_dir, logs_dir, reports_dir, state_dir, lineage_manifests_dir]:
            ensure_dir(directory)
        self.workspace.migrate_logs_dir(legacy_logs_dir, logs_dir)
        return ProjectPaths(
            workspace_root=context.paths.workspace_root,
            projects_root=context.paths.projects_root,
            project_root=integration_root,
            repo_dir=worktree_dir,
            docs_dir=docs_dir,
            memory_dir=memory_dir,
            logs_dir=logs_dir,
            reports_dir=reports_dir,
            state_dir=state_dir,
            metadata_file=integration_root / "metadata.json",
            project_config_file=integration_root / "project_config.json",
            loop_state_file=state_dir / "LOOP_STATE.json",
            plan_file=docs_dir / "PLAN.md",
            mid_term_plan_file=docs_dir / "MID_TERM_PLAN.md",
            scope_guard_file=docs_dir / "SCOPE_GUARD.md",
            active_task_file=docs_dir / "ACTIVE_TASK.md",
            block_review_file=docs_dir / "BLOCK_REVIEW.md",
            checkpoint_timeline_file=docs_dir / "CHECKPOINT_TIMELINE.md",
            research_notes_file=docs_dir / "RESEARCH_NOTES.md",
            attempt_history_file=docs_dir / "attempt_history.md",
            success_patterns_file=memory_dir / "success_patterns.jsonl",
            failure_patterns_file=memory_dir / "failure_patterns.jsonl",
            task_summaries_file=memory_dir / "task_summaries.jsonl",
            pass_log_file=logs_dir / "passes.jsonl",
            block_log_file=logs_dir / "blocks.jsonl",
            planning_metrics_file=logs_dir / "planning_metrics.jsonl",
            checkpoint_state_file=state_dir / "CHECKPOINTS.json",
            execution_plan_file=state_dir / "EXECUTION_PLAN.json",
            planning_inputs_cache_file=state_dir / "PLANNING_INPUTS_CACHE.json",
            planning_prompt_cache_file=state_dir / "PLANNING_PROMPT_CACHE.json",
            block_plan_cache_file=state_dir / "BLOCK_PLAN_CACHE.json",
            lineage_state_file=state_dir / "LINEAGES.json",
            spine_file=state_dir / "SPINE.json",
            common_requirements_file=state_dir / "COMMON_REQUIREMENTS.json",
            contract_wave_audit_file=state_dir / "CONTRACT_WAVE_AUDIT.jsonl",
            ml_mode_state_file=state_dir / "ML_MODE_STATE.json",
            ml_step_report_file=state_dir / "ML_STEP_REPORT.json",
            ml_experiment_reports_dir=state_dir / "ml_experiments",
            lineage_manifests_dir=lineage_manifests_dir,
            ui_control_file=state_dir / "UI_RUN_CONTROL.json",
            ui_event_log_file=logs_dir / "ui_events.jsonl",
            execution_flow_svg_file=docs_dir / "EXECUTION_FLOW.svg",
            closeout_report_file=docs_dir / "CLOSEOUT_REPORT.md",
            closeout_report_docx_file=reports_dir / "CLOSEOUT_REPORT.docx",
            closeout_report_pptx_file=reports_dir / "CLOSEOUT_REPORT.pptx",
            ml_experiment_report_file=docs_dir / "ML_EXPERIMENT_REPORT.md",
            ml_experiment_results_svg_file=docs_dir / "ML_EXPERIMENT_RESULTS.svg",
            shared_contracts_file=docs_dir / "SHARED_CONTRACTS.md",
        )
    def _build_integration_context(
        self,
        context: ProjectContext,
        runtime: RuntimeOptions,
        step: ExecutionStep,
        base_revision: str,
        integration_token: str,
    ) -> dict[str, object]:
        integration_root = self._integration_root(context, integration_token)
        worktree_dir = integration_root / "repo"
        branch_name = self._integration_branch_name(step, integration_token)
        self.git.add_worktree(context.paths.repo_dir, worktree_dir, branch_name, base_revision)
        integration_paths = self._build_integration_paths(context, integration_token, worktree_dir)
        self._sync_lineage_support_files(context, integration_paths)
        integration_runtime = self._build_parallel_worker_runtime(runtime, step)
        integration_metadata = RepoMetadata(
            repo_id=f"{context.metadata.repo_id}:integration:{integration_token}",
            slug=f"{context.metadata.slug}-integration-{integration_token}",
            repo_url=context.metadata.repo_url,
            branch=branch_name,
            project_root=integration_paths.project_root,
            repo_path=worktree_dir,
            created_at=now_utc_iso(),
            last_run_at=None,
            current_status="integration_ready",
            current_safe_revision=base_revision,
            repo_kind=context.metadata.repo_kind,
            display_name=f"{context.metadata.display_name or context.metadata.slug} [integration {step.step_id}]",
            origin_url=context.metadata.origin_url,
            source_repo_id=context.metadata.source_repo_id or context.metadata.repo_id,
        )
        integration_loop_state = LoopState(
            repo_id=integration_metadata.repo_id,
            repo_slug=integration_metadata.slug,
            current_safe_revision=base_revision,
        )
        integration_context = ProjectContext(
            metadata=integration_metadata,
            runtime=integration_runtime,
            paths=integration_paths,
            loop_state=integration_loop_state,
        )
        self._sync_child_execution_plan_state(context, integration_context)
        self._ensure_project_documents(integration_context)
        self._persist_context_files(integration_context)
        return {
            "branch_name": branch_name,
            "integration_root": integration_root,
            "integration_context": integration_context,
            "worktree_dir": worktree_dir,
            "token": integration_token,
        }
    def _cleanup_integration_worktree(self, repo_dir: Path, integration_info: dict[str, object]) -> None:
        worktree_dir = integration_info.get("worktree_dir")
        branch_name = str(integration_info.get("branch_name") or "").strip()
        if isinstance(worktree_dir, Path):
            self.git.remove_worktree(repo_dir, worktree_dir, force=True)
        if branch_name:
            self.git.delete_branch(repo_dir, branch_name, force=True)
    def _merge_targets_for_lineages(self, plan_state: ExecutionPlanState, step: ExecutionStep) -> list[str]:
        metadata = step.metadata if isinstance(step.metadata, dict) else {}
        return self._coerce_string_list(metadata.get("merge_from", [])) or list(step.depends_on)
    def _build_join_merge_step(
        self,
        plan_state: ExecutionPlanState,
        step: ExecutionStep,
        merge_targets: list[str],
    ) -> ExecutionStep:
        step_by_id = {item.step_id: item for item in plan_state.steps}
        ordered_paths: list[str] = []
        seen_paths: set[str] = set()
        upstream_titles: list[str] = []
        for step_id in merge_targets:
            upstream_step = step_by_id.get(step_id)
            if upstream_step is None:
                continue
            if upstream_step.title.strip():
                upstream_titles.append(upstream_step.title.strip())
            for path in upstream_step.owned_paths:
                normalized = self._normalize_owned_path(path)
                if not normalized or normalized in seen_paths:
                    continue
                seen_paths.add(normalized)
                ordered_paths.append(normalized)
        for path in step.owned_paths:
            normalized = self._normalize_owned_path(path)
            if not normalized or normalized in seen_paths:
                continue
            seen_paths.add(normalized)
            ordered_paths.append(normalized)
        metadata = deepcopy(step.metadata) if isinstance(step.metadata, dict) else {}
        metadata["merge_phase"] = "integration"
        metadata["merge_targets"] = merge_targets
        if upstream_titles:
            metadata["parallel_step_titles"] = upstream_titles
        return normalize_execution_step_policy(
            ExecutionStep(
            step_id=f"{step.step_id}-MERGE",
            title=f"Resolve integration merge for {step.step_id}",
            display_description=f"Resolve merge conflicts while integrating {', '.join(merge_targets) or step.step_id}.",
            codex_description=(
                "Resolve the current cherry-pick conflict inside the integration worktree, preserve the intent of all "
                "upstream branches, and proactively repair adjacent compatibility issues exposed by the merge so the "
                "worktree is ready for the remaining merges or verification."
            ),
            test_command=step.test_command,
            success_criteria=(
                "The merge conflict is resolved cleanly, targeted integration fixes are applied where needed, and the "
                "integration worktree can continue."
            ),
            reasoning_effort="high",
            depends_on=merge_targets,
            owned_paths=ordered_paths,
            step_type="integration",
            scope_class="shared_reviewed",
            spine_version=step.spine_version,
            shared_contracts=list(step.shared_contracts),
            metadata=metadata,
            ),
            current_spine_version=step.spine_version or DEFAULT_SPINE_VERSION,
        )
    def _build_parallel_batch_merge_step(
        self,
        steps: list[ExecutionStep],
        test_command: str,
    ) -> ExecutionStep:
        step_ids = [step.step_id for step in steps if step.step_id.strip()]
        titles = ", ".join(step_ids) if step_ids else "parallel batch"
        parallel_step_titles = [step.title.strip() for step in steps if step.title.strip()]
        ordered_paths: list[str] = []
        seen_paths: set[str] = set()
        for step in steps:
            for path in step.owned_paths:
                normalized = self._normalize_owned_path(path)
                if not normalized or normalized in seen_paths:
                    continue
                seen_paths.add(normalized)
                ordered_paths.append(normalized)
        return normalize_execution_step_policy(
            ExecutionStep(
            step_id="BATCH-MERGE",
            title=f"Resolve merged parallel batch conflict {titles}",
            display_description=f"Resolve cherry-pick conflicts while merging {titles}.",
            codex_description=(
                "Resolve the current cherry-pick conflict for the merged parallel batch, preserve the intent of all "
                "completed worker branches, and proactively repair adjacent compatibility issues exposed by the merge "
                "so the repository is ready for verification."
            ),
            test_command=test_command,
            success_criteria=(
                "The merged parallel batch cherry-pick conflict is resolved cleanly and any directly exposed "
                "integration inconsistencies are repaired."
            ),
            reasoning_effort="high",
            depends_on=step_ids,
            owned_paths=ordered_paths,
            step_type="integration",
            scope_class="shared_reviewed",
            metadata={"parallel_step_titles": parallel_step_titles, "merge_phase": "parallel_batch"},
            ),
            current_spine_version=DEFAULT_SPINE_VERSION,
        )
    def _normalize_hybrid_step_kind(self, value: object) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {"join", "barrier"}:
            return normalized
        return "task"
    def _step_kind(self, step: ExecutionStep) -> str:
        metadata = step.metadata if isinstance(step.metadata, dict) else {}
        return self._normalize_hybrid_step_kind(metadata.get("step_kind", ""))
    def _normalize_join_policy(self, value: object) -> str:
        normalized = str(value or "").strip().lower()
        return normalized or "all"
    def _normalize_hybrid_step_metadata(self, steps: list[ExecutionStep]) -> None:
        for step in steps:
            metadata = deepcopy(step.metadata) if isinstance(step.metadata, dict) else {}
            step_kind = self._normalize_hybrid_step_kind(metadata.get("step_kind", ""))
            if step_kind != "task":
                metadata["step_kind"] = step_kind
            else:
                metadata.pop("step_kind", None)
            if step_kind == "join":
                direct_dependencies = list(step.depends_on)
                merge_from = [item for item in self._coerce_string_list(metadata.get("merge_from", [])) if item in direct_dependencies]
                if len(merge_from) < 2:
                    merge_from = direct_dependencies
                metadata["merge_from"] = merge_from
                metadata["join_policy"] = self._normalize_join_policy(metadata.get("join_policy", ""))
            else:
                metadata.pop("merge_from", None)
                metadata.pop("join_policy", None)
            step.metadata = metadata
