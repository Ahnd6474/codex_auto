from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import shutil
from uuid import uuid4

from .codex_runner import CodexRunner
from .errors import (
    ExecutionFailure,
    ExecutionPreflightError,
    HANDLED_OPERATION_EXCEPTIONS,
    ParallelExecutionFailure,
    failure_log_fields,
)
from .execution_control import ImmediateStopRequested
from .memory import MemoryStore
from .models import CandidateTask, ExecutionPlanState, ExecutionStep, LoopState, ProjectContext, ProjectPaths, RepoMetadata, RuntimeOptions
from .parallel_resources import build_parallel_resource_plan
from .reporting import Reporter
from .utils import compact_text, ensure_dir, now_utc_iso, read_json, read_last_jsonl, remove_tree, write_json
from .workspace import WorkspaceManager


class OrchestratorParallelMixin:
    def _parallel_worker_plan(self, runtime: RuntimeOptions):
        return build_parallel_resource_plan(
            getattr(runtime, "parallel_worker_mode", "auto"),
            getattr(runtime, "parallel_workers", 0),
            getattr(runtime, "parallel_memory_per_worker_gib", 3),
        )

    def _parallel_worker_count(self, runtime: RuntimeOptions) -> int:
        return self._parallel_worker_plan(runtime).recommended_workers

    def _parallel_batch_token(self) -> str:
        return f"pr-{uuid4().hex[:10]}"

    def _parallel_worker_slug(self, step: ExecutionStep, worker_index: int) -> str:
        raw = f"{worker_index:02d}-{step.step_id.strip().lower() or 'step'}"
        return "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in raw).strip("-") or f"worker-{worker_index:02d}"

    def _build_parallel_worker_runtime(
        self,
        runtime: RuntimeOptions,
        step: ExecutionStep,
    ) -> RuntimeOptions:
        return self._build_execution_step_runtime(
            runtime,
            step,
            execution_mode="parallel",
            parallel_workers=1,
            max_blocks=1,
            allow_push=False,
            require_checkpoint_approval=False,
            checkpoint_interval_blocks=1,
        )

    def _build_parallel_worker_paths(
        self,
        context: ProjectContext,
        batch_token: str,
        worker_slug: str,
        worktree_dir: Path,
    ) -> ProjectPaths:
        worker_root = context.paths.project_root / ".parallel_runs" / batch_token / worker_slug
        docs_dir = worker_root / "docs"
        memory_dir = worker_root / "memory"
        legacy_logs_dir = worker_root / "logs"
        logs_dir = WorkspaceManager.repo_logs_dir(worktree_dir)
        reports_dir = worker_root / "reports"
        state_dir = worker_root / "state"
        lineage_manifests_dir = state_dir / "lineage_manifests"
        for directory in [worker_root, docs_dir, memory_dir, logs_dir, reports_dir, state_dir, lineage_manifests_dir]:
            ensure_dir(directory)
        self.workspace.migrate_logs_dir(legacy_logs_dir, logs_dir)
        return ProjectPaths(
            workspace_root=context.paths.workspace_root,
            projects_root=context.paths.projects_root,
            project_root=worker_root,
            repo_dir=worktree_dir,
            docs_dir=docs_dir,
            memory_dir=memory_dir,
            logs_dir=logs_dir,
            reports_dir=reports_dir,
            state_dir=state_dir,
            metadata_file=worker_root / "metadata.json",
            project_config_file=worker_root / "project_config.json",
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

    def _parallel_worker_state_copy_pairs(
        self,
        context: ProjectContext,
        worker_paths: ProjectPaths,
    ) -> list[tuple[Path, Path]]:
        return [
            (context.paths.execution_plan_file, worker_paths.execution_plan_file),
            (context.paths.checkpoint_state_file, worker_paths.checkpoint_state_file),
            (context.paths.lineage_state_file, worker_paths.lineage_state_file),
            (context.paths.spine_file, worker_paths.spine_file),
            (context.paths.common_requirements_file, worker_paths.common_requirements_file),
            (context.paths.contract_wave_audit_file, worker_paths.contract_wave_audit_file),
            (context.paths.ml_mode_state_file, worker_paths.ml_mode_state_file),
            (context.paths.ui_control_file, worker_paths.ui_control_file),
        ]

    def _copy_parallel_worker_support_files(self, context: ProjectContext, worker_paths: ProjectPaths) -> None:
        for source_dir, target_dir in [
            (context.paths.docs_dir, worker_paths.docs_dir),
            (context.paths.memory_dir, worker_paths.memory_dir),
        ]:
            ensure_dir(target_dir)
            if source_dir.exists():
                shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)

        for source_path, target_path in self._parallel_worker_state_copy_pairs(context, worker_paths):
            if not source_path.exists():
                continue
            ensure_dir(target_path.parent)
            shutil.copy2(source_path, target_path)

        if context.paths.lineage_manifests_dir.exists():
            ensure_dir(worker_paths.lineage_manifests_dir)
            shutil.copytree(
                context.paths.lineage_manifests_dir,
                worker_paths.lineage_manifests_dir,
                dirs_exist_ok=True,
            )

    def _build_parallel_worker_context(
        self,
        context: ProjectContext,
        runtime: RuntimeOptions,
        step: ExecutionStep,
        base_revision: str,
        batch_token: str,
        worker_index: int,
    ) -> dict[str, object]:
        worker_slug = self._parallel_worker_slug(step, worker_index)
        worker_root = context.paths.project_root / ".parallel_runs" / batch_token / worker_slug
        worktree_dir = worker_root / "repo"
        branch_name = f"jakal-flow-parallel-{batch_token}-{worker_slug}"
        self.git.add_worktree(context.paths.repo_dir, worktree_dir, branch_name, base_revision)
        worker_paths = self._build_parallel_worker_paths(context, batch_token, worker_slug, worktree_dir)
        self._copy_parallel_worker_support_files(context, worker_paths)
        worker_runtime = self._build_parallel_worker_runtime(runtime, step)
        worker_metadata = RepoMetadata(
            repo_id=f"{context.metadata.repo_id}:{step.step_id.lower()}",
            slug=f"{context.metadata.slug}-{worker_slug}",
            repo_url=context.metadata.repo_url,
            branch=branch_name,
            project_root=worker_paths.project_root,
            repo_path=worktree_dir,
            created_at=now_utc_iso(),
            last_run_at=None,
            current_status="parallel_worker_ready",
            current_safe_revision=base_revision,
            repo_kind=context.metadata.repo_kind,
            display_name=f"{context.metadata.display_name or context.metadata.slug} [{step.step_id}]",
            origin_url=context.metadata.origin_url,
            source_repo_id=context.metadata.source_repo_id or context.metadata.repo_id,
        )
        worker_loop_state = LoopState(
            repo_id=worker_metadata.repo_id,
            repo_slug=worker_metadata.slug,
            current_safe_revision=base_revision,
        )
        worker_context = ProjectContext(
            metadata=worker_metadata,
            runtime=worker_runtime,
            paths=worker_paths,
            loop_state=worker_loop_state,
        )
        self._ensure_project_documents(worker_context)
        write_json(worker_paths.metadata_file, worker_metadata.to_dict())
        write_json(worker_paths.project_config_file, worker_runtime.to_dict())
        write_json(worker_paths.loop_state_file, worker_loop_state.to_dict())
        return {
            "branch_name": branch_name,
            "worker_root": worker_root,
            "worker_context": worker_context,
            "worktree_dir": worktree_dir,
        }

    def _sync_parallel_batch_step_progress(
        self,
        *,
        context: ProjectContext,
        plan_state: ExecutionPlanState,
        ordered_targets: list[ExecutionStep],
        step_id: str,
        worker_result: dict[str, object],
        success_status: str,
        running_status: str,
        failure_status: str = "failed",
        failure_project_status: str = "failed",
    ) -> tuple[ExecutionPlanState, list[ExecutionStep]]:
        step_by_id = {step.step_id: step for step in plan_state.steps}
        step = step_by_id.get(step_id.strip())
        if step is None:
            return plan_state, ordered_targets

        synced_at = now_utc_iso()
        result_status = str(worker_result.get("status") or "").strip().lower() or "failed"
        worker_note = str(worker_result.get("test_summary") or worker_result.get("notes") or "").strip()
        worker_commit = str(worker_result.get("commit_hash") or "").strip()
        metadata = deepcopy(step.metadata) if isinstance(step.metadata, dict) else {}
        metadata["parallel_worker_status"] = result_status
        metadata["parallel_worker_synced_at"] = synced_at
        if worker_commit:
            metadata["parallel_worker_commit_hash"] = worker_commit
        else:
            metadata.pop("parallel_worker_commit_hash", None)
        step.metadata = metadata

        if result_status == "completed":
            step.status = success_status
            self._clear_step_failure_metadata(step)
            if success_status == "completed":
                step.completed_at = synced_at
                step.commit_hash = worker_commit or None
                step.notes = worker_note or "Parallel lineage worker completed."
            else:
                step.completed_at = None
                step.commit_hash = None
                step.notes = worker_note or "Parallel worker finished and is waiting for batch integration."
            context.metadata.current_status = running_status
        elif result_status == "paused":
            step.status = "paused"
            step.completed_at = None
            step.commit_hash = None
            step.notes = worker_note or "Immediate stop requested."
            self._clear_step_failure_metadata(step)
            context.metadata.current_status = self._status_from_plan_state(plan_state)
        else:
            step.status = failure_status
            step.completed_at = None
            step.commit_hash = None
            step.notes = worker_note or ("Parallel worker recovery pending." if failure_status == "pending" else "Parallel worker failed.")
            if failure_status == "pending":
                self._clear_step_failure_metadata(step)
            else:
                self._set_step_failure_from_worker_result(step, worker_result)
            context.metadata.current_status = failure_project_status

        context.metadata.last_run_at = synced_at
        plan_state = self.save_execution_plan_state(context, plan_state)
        self.workspace.save_project(context)
        refreshed_targets = {item.step_id: item for item in plan_state.steps}
        return plan_state, [refreshed_targets.get(item.step_id, item) for item in ordered_targets]

    def _parallel_worker_status(self, worker_result: dict[str, object]) -> str:
        return str(worker_result.get("status") or "").strip().lower() or "failed"

    def _parallel_partial_failure_details(
        self,
        ordered_targets: list[ExecutionStep],
        worker_results: list[dict[str, object]],
    ) -> tuple[str, dict[str, object]]:
        result_by_step = {
            str(result.get("step_id") or "").strip(): result
            for result in worker_results
            if str(result.get("step_id") or "").strip()
        }
        completed_steps: list[str] = []
        failed_steps: list[dict[str, str]] = []
        for step in ordered_targets:
            worker_result = result_by_step.get(step.step_id, {})
            status = self._parallel_worker_status(worker_result)
            if status == "completed":
                completed_steps.append(step.step_id)
                continue
            if status != "failed":
                continue
            failed_steps.append(
                {
                    "step_id": step.step_id,
                    "note": str(worker_result.get("notes") or "Parallel worker failed.").strip() or "Parallel worker failed.",
                }
            )
        summary_parts: list[str] = ["Parallel batch partially completed." if completed_steps else "Parallel batch failed."]
        if completed_steps:
            summary_parts.append(f"Completed and kept: {', '.join(completed_steps)}.")
        if failed_steps:
            failure_details = "; ".join(f"{item['step_id']} ({item['note']})" for item in failed_steps)
            summary_parts.append(f"Failed: {failure_details}.")
        return " ".join(summary_parts).strip(), {
            "partial_success": bool(completed_steps),
            "completed_steps": completed_steps,
            "failed_steps": failed_steps,
        }

    def _apply_parallel_batch_outcomes(
        self,
        ordered_targets: list[ExecutionStep],
        worker_results: list[dict[str, object]],
        *,
        completed_step_ids: set[str],
        merged_commit_by_step_id: dict[str, str],
        completed_note: str,
    ) -> None:
        result_by_step = {
            str(result.get("step_id") or "").strip(): result
            for result in worker_results
            if str(result.get("step_id") or "").strip()
        }
        completed_at = now_utc_iso()
        for step in ordered_targets:
            worker_result = result_by_step.get(step.step_id, {})
            if step.step_id in completed_step_ids:
                step.status = "completed"
                step.completed_at = completed_at
                step.commit_hash = str(merged_commit_by_step_id.get(step.step_id, "") or "").strip() or None
                worker_note = str(worker_result.get("test_summary") or "").strip()
                step.notes = worker_note or completed_note
                self._clear_step_failure_metadata(step)
                continue
            step.status = "failed"
            step.completed_at = None
            step.commit_hash = None
            step.notes = str(worker_result.get("notes") or "Parallel worker failed.").strip() or "Parallel worker failed."
            self._set_step_failure_from_worker_result(step, worker_result)

    def _refresh_ordered_targets(
        self,
        plan_state: ExecutionPlanState,
        ordered_targets: list[ExecutionStep],
    ) -> list[ExecutionStep]:
        refreshed_targets = {step.step_id: step for step in plan_state.steps}
        return [refreshed_targets.get(step.step_id, step) for step in ordered_targets]

    def _defer_parallel_recovery_step(
        self,
        *,
        context: ProjectContext,
        step_id: str,
        note: str,
        ordered_targets: list[ExecutionStep],
    ) -> tuple[ExecutionPlanState, list[ExecutionStep], ExecutionStep]:
        plan_state = self.load_execution_plan_state(context)
        target_step = next((step for step in plan_state.steps if step.step_id == step_id.strip()), None)
        if target_step is None:
            raise RuntimeError(f"{step_id} could not be found while deferring parallel recovery.")
        target_step.status = "pending"
        target_step.completed_at = None
        target_step.commit_hash = None
        target_step.notes = note.strip() or "Automatic recovery deferred this step for retry."
        context.metadata.current_status = self._status_from_plan_state(plan_state)
        context.metadata.last_run_at = now_utc_iso()
        saved = self.save_execution_plan_state(context, plan_state)
        self.workspace.save_project(context)
        refreshed_targets = self._refresh_ordered_targets(saved, ordered_targets)
        refreshed_step = next((step for step in refreshed_targets if step.step_id == target_step.step_id), target_step)
        return saved, refreshed_targets, refreshed_step

    def _run_parallel_serial_recovery(
        self,
        *,
        context: ProjectContext,
        runtime: RuntimeOptions,
        ordered_targets: list[ExecutionStep],
        recovery_step_ids: list[str],
    ) -> tuple[ExecutionPlanState, list[ExecutionStep], str, str]:
        attempted_steps: list[str] = []
        plan_state = self.load_execution_plan_state(context)
        ordered_targets = self._refresh_ordered_targets(plan_state, ordered_targets)

        for step_id in recovery_step_ids:
            try:
                context, plan_state, result_step = self._run_saved_execution_step_with_context(
                    context=context,
                    runtime=runtime,
                    step_id=step_id,
                    allow_push=False,
                    final_failure_reports=False,
                )
            except HANDLED_OPERATION_EXCEPTIONS as exc:
                deferred_note = (
                    f"{str(exc).strip() or 'Automatic serial recovery failed.'} "
                    "Automatic recovery deferred this step for retry."
                ).strip()
                plan_state, ordered_targets, _ = self._defer_parallel_recovery_step(
                    context=context,
                    step_id=step_id,
                    note=deferred_note,
                    ordered_targets=ordered_targets,
                )
                return plan_state, ordered_targets, "deferred", deferred_note

            ordered_targets = self._refresh_ordered_targets(plan_state, ordered_targets)
            result_step = next((step for step in ordered_targets if step.step_id == step_id.strip()), result_step)
            if result_step.status == "completed":
                attempted_steps.append(step_id)
                continue
            if result_step.status == "paused":
                return plan_state, ordered_targets, "paused", result_step.notes or "Immediate stop requested."

            deferred_note = (
                f"{result_step.notes or 'Automatic serial recovery did not converge.'} "
                "Automatic recovery deferred this step for retry."
            ).strip()
            plan_state, ordered_targets, _ = self._defer_parallel_recovery_step(
                context=context,
                step_id=step_id,
                note=deferred_note,
                ordered_targets=ordered_targets,
            )
            return plan_state, ordered_targets, "deferred", deferred_note

        summary = (
            f"Parallel batch recovered successfully after serial fallback for {', '.join(attempted_steps)}."
            if attempted_steps
            else "Parallel batch recovery did not require any serial fallback steps."
        )
        if attempted_steps:
            last_commit = str(context.metadata.current_safe_revision or context.loop_state.current_safe_revision or "").strip()
            if last_commit:
                pushed, push_reason = self._push_if_ready(
                    context,
                    context.paths.repo_dir,
                    context.metadata.branch,
                    commit_hash=last_commit,
                )
                if not pushed and push_reason not in {"already_up_to_date"}:
                    summary = f"{summary} | push skipped: {push_reason}".strip(" |")
        plan_state = self.load_execution_plan_state(context)
        ordered_targets = self._refresh_ordered_targets(plan_state, ordered_targets)
        context.metadata.current_status = self._status_from_plan_state(plan_state)
        context.metadata.last_run_at = now_utc_iso()
        self.workspace.save_project(context)
        return plan_state, ordered_targets, "completed", summary

    def _parallel_batch_log_status(self, step_status: str) -> str:
        normalized = str(step_status or "").strip().lower()
        if normalized in {"completed", "paused", "pending"}:
            return normalized
        return "failed"

    def _parallel_batch_attempt_status(self, step_status: str) -> str:
        normalized = str(step_status or "").strip().lower()
        if normalized == "completed":
            return "completed"
        if normalized == "paused":
            return "parallel batch paused"
        if normalized == "pending":
            return "parallel batch deferred"
        return "parallel batch failed"

    def _run_parallel_step_worker(
        self,
        context: ProjectContext,
        runtime: RuntimeOptions,
        step: ExecutionStep,
        base_revision: str,
        batch_token: str,
        worker_index: int,
    ) -> dict[str, object]:
        worker_slug = self._parallel_worker_slug(step, worker_index)
        worker_root = context.paths.project_root / ".parallel_runs" / batch_token / worker_slug
        worktree_dir = worker_root / "repo"
        branch_name = f"jakal-flow-parallel-{batch_token}-{worker_slug}"
        worker_result: dict[str, object] = {
            "step_id": step.step_id,
            "lineage_id": str((step.metadata if isinstance(step.metadata, dict) else {}).get("lineage_id", "")).strip(),
            "status": "failed",
            "notes": "Parallel worker did not complete.",
            "commit_hash": None,
            "changed_files": [],
            "branch_name": branch_name,
            "worktree_dir": worktree_dir,
            "worker_root": worker_root,
            "pass_log": {},
            "block_log": {},
            "test_summary": "",
            "ml_report_payload": {},
        }
        worker_runtime = self._build_parallel_worker_runtime(runtime, step)
        preflight_error = self._execution_runtime_preflight_error(context, worker_runtime)
        if preflight_error:
            failure = ExecutionPreflightError(preflight_error)
            worker_result["status"] = "failed"
            worker_result["notes"] = str(failure)
            worker_result["test_summary"] = str(failure)
            worker_result.update(failure_log_fields(failure))
            return worker_result
        try:
            worker_info = self._build_parallel_worker_context(context, runtime, step, base_revision, batch_token, worker_index)
            worker_context = worker_info["worker_context"]
            if not isinstance(worker_context, ProjectContext):
                raise RuntimeError("Parallel worker context could not be created.")
            candidate = CandidateTask(
                candidate_id=step.step_id,
                title=step.title,
                rationale=self._execution_step_rationale(step, worker_context.runtime.test_cmd),
                plan_refs=[step.step_id],
                score=1.0,
            )
            runner = CodexRunner(worker_context.runtime.codex_path)
            memory = MemoryStore(worker_context.paths)
            reporter = Reporter(worker_context)
            latest_block, _attempt_count = self._run_execution_step_attempts(
                context=worker_context,
                runner=runner,
                memory=memory,
                reporter=reporter,
                candidate=candidate,
                execution_step=deepcopy(step),
                final_failure_reports=False,
            )
            latest_block = latest_block or {}
            latest_pass = read_last_jsonl(worker_context.paths.pass_log_file) or {}
            changed_files = latest_block.get("changed_files", latest_pass.get("changed_files", []))
            commit_hashes = latest_block.get("commit_hashes", [])
            commit_hash = None
            if isinstance(commit_hashes, list) and commit_hashes:
                commit_hash = str(commit_hashes[-1]).strip() or None
            worker_status = "completed" if latest_block.get("status") == "completed" else "failed"
            block_summary = str(latest_block.get("test_summary") or "").strip()
            worker_summary = self._parallel_worker_summary(latest_block, latest_pass)
            step_metadata = step.metadata if isinstance(step.metadata, dict) else {}
            lineage_id = str(
                worker_result.get("lineage_id")
                or latest_block.get("lineage_id")
                or latest_pass.get("lineage_id")
                or step_metadata.get("lineage_id", "")
            ).strip()
            summary_for_log = Reporter.summarize_logged_result(
                block_entry=latest_block,
                pass_entry=latest_pass,
                completed_summary="Parallel worker finished.",
                failed_summary="Parallel worker failed.",
            )
            worker_result.update(
                {
                    "status": worker_status,
                    "lineage_id": lineage_id,
                    "notes": worker_summary,
                    "commit_hash": commit_hash,
                    "changed_files": [
                        str(item).strip()
                        for item in changed_files
                        if str(item).strip()
                    ]
                    if isinstance(changed_files, list)
                    else [],
                    "pass_log": latest_pass,
                    "block_log": latest_block,
                    "test_summary": summary_for_log if (worker_status != "completed" or not block_summary) else block_summary,
                    "failure_type": str(latest_block.get("failure_type") or latest_pass.get("failure_type") or "").strip(),
                    "failure_reason_code": str(
                        latest_block.get("failure_reason_code") or latest_pass.get("failure_reason_code") or ""
                    ).strip(),
                    "ml_report_payload": read_json(worker_context.paths.ml_step_report_file, default={}),
                }
            )
        except ImmediateStopRequested as exc:
            worker_result["status"] = "paused"
            worker_result["notes"] = str(exc).strip() or "Immediate stop requested."
        except HANDLED_OPERATION_EXCEPTIONS as exc:
            failure = exc if isinstance(exc, ExecutionFailure) else ParallelExecutionFailure(
                str(exc).strip() or "Parallel worker failed."
            )
            worker_result["status"] = "failed"
            worker_result["notes"] = str(failure)
            worker_result.update(failure_log_fields(failure))
        return worker_result

    def _parallel_worker_summary(
        self,
        latest_block: dict[str, object],
        latest_pass: dict[str, object],
    ) -> str:
        return Reporter.summarize_logged_result(
            block_entry=latest_block,
            pass_entry=latest_pass,
            completed_summary="Parallel worker finished.",
            failed_summary="Parallel worker failed.",
        )

    def _cleanup_parallel_worker(self, repo_dir: Path, worker_result: dict[str, object]) -> None:
        worktree_dir = worker_result.get("worktree_dir")
        branch_name = str(worker_result.get("branch_name") or "").strip()
        worker_root = worker_result.get("worker_root")
        if isinstance(worktree_dir, Path):
            self.git.remove_worktree(repo_dir, worktree_dir, force=True)
        if branch_name:
            self.git.delete_branch(repo_dir, branch_name, force=True)
        if isinstance(worker_root, Path):
            remove_tree(worker_root, ignore_errors=True)
