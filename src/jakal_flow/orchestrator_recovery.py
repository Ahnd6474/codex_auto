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
from .environment import ensure_gitignore, ensure_virtualenv
from . import execution_plan_support
from .codex_runner import CodexRunner
from .errors import (
    AgentPassExecutionError,
    MergeConflictStateError,
    MissingRecoveryArtifactsError,
    ParallelMergeConflictError,
    VerificationTestFailure,
)
from .execution_control import ImmediateStopRequested
from .git_ops import GitOps
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


class OrchestratorRecoveryMixin:
    def _debug_pass_name(self, pass_name: str) -> str:
        normalized = str(pass_name).strip() or "debug"
        if normalized.endswith("-pass"):
            return f"{normalized[:-5]}-debug"
        return f"{normalized}-debug"
    def _merge_pass_name(self, pass_name: str) -> str:
        normalized = str(pass_name).strip() or "merge"
        if normalized.endswith("-pass"):
            return f"{normalized[:-5]}-merger"
        if normalized.endswith("-merge"):
            return f"{normalized[:-6]}-merger"
        return f"{normalized}-merger"
    def _log_pass_result(
        self,
        *,
        context: ProjectContext,
        reporter: Reporter,
        block_index: int,
        candidate: CandidateTask,
        pass_name: str,
        run_result,
        test_result: TestRunResult | None,
        commit_hash: str | None,
        rollback_status: str,
        search_enabled: bool,
    ) -> None:
        reporter.log_pass(
            {
                "repository_id": context.metadata.repo_id,
                "repository_slug": context.metadata.slug,
                "block_index": block_index,
                "pass_type": pass_name,
                "selected_task": candidate.title,
                "changed_files": run_result.changed_files,
                "test_results": test_result.to_dict() if test_result else None,
                "usage": run_result.usage,
                "duration_seconds": run_result.duration_seconds,
                "codex_attempt_count": run_result.attempt_count,
                "codex_diagnostics": run_result.diagnostics,
                "codex_return_code": run_result.returncode,
                "commit_hash": commit_hash,
                "rollback_status": rollback_status,
                "search_enabled": search_enabled,
            }
        )
    def _run_debugger_pass(
        self,
        *,
        context: ProjectContext,
        runner: CodexRunner,
        reporter: Reporter,
        block_index: int,
        candidate: CandidateTask,
        execution_step: ExecutionStep | None,
        memory_context: str,
        failing_pass_name: str,
        failing_test_result: TestRunResult,
        post_success_strategy: str = "commit_if_changes",
    ):
        debug_pass_name = self._debug_pass_name(failing_pass_name)
        debugger_prompt_template = load_debugger_prompt_template(context.runtime.execution_mode)
        previous_status = context.metadata.current_status
        previous_task = context.loop_state.current_task
        context.metadata.current_status = "running:debugging"
        context.metadata.last_run_at = now_utc_iso()
        context.loop_state.current_task = f"Debugging {candidate.title}".strip()
        self.workspace.save_project(context)
        prompt = debugger_prompt(
            context=context,
            candidate=candidate,
            memory_context=memory_context,
            failing_pass_name=failing_pass_name,
            failing_test_summary=failing_test_result.summary,
            failing_test_stdout=read_text(failing_test_result.stdout_file),
            failing_test_stderr=read_text(failing_test_result.stderr_file),
            execution_step=execution_step,
            template_text=debugger_prompt_template,
        )
        try:
            run_result = self._run_pass_with_provider_fallback(
                context=context,
                runner=runner,
                prompt=prompt,
                pass_type=debug_pass_name,
                block_index=block_index,
                search_enabled=False,
                execution_step=execution_step,
            )
            run_result.changed_files = self.git.changed_files(context.paths.repo_dir)
            if run_result.returncode != 0:
                return debug_pass_name, run_result, None, None

            test_result = self._run_test_command(context, block_index, debug_pass_name)
            test_result.summary = f"{test_result.summary} after debugger recovery"
            reporter.save_test_result(block_index, debug_pass_name, test_result)
            commit_hash: str | None = None
            if test_result.returncode == 0:
                commit_descriptor = build_commit_descriptor(
                    context,
                    debug_pass_name,
                    candidate.title,
                    execution_step=execution_step,
                )
                if post_success_strategy == "commit_if_changes":
                    if self.git.has_changes(context.paths.repo_dir):
                        commit_hash = self.git.commit_all(
                            context.paths.repo_dir,
                            commit_descriptor.message,
                            author_name=commit_descriptor.author_name,
                        )
                elif post_success_strategy == "continue_cherry_pick":
                    if self.git.cherry_pick_in_progress(context.paths.repo_dir):
                        self.git.add_all(context.paths.repo_dir)
                        commit_hash = self.git.commit_staged(
                            context.paths.repo_dir,
                            commit_descriptor.message,
                            author_name=commit_descriptor.author_name,
                        )
                    else:
                        commit_hash = self.git.current_revision(context.paths.repo_dir)
                else:
                    raise ValueError(f"Unsupported debugger success strategy: {post_success_strategy}")
            return debug_pass_name, run_result, test_result, commit_hash
        finally:
            context.metadata.last_run_at = now_utc_iso()
            if context.metadata.current_status == "running:debugging":
                context.metadata.current_status = previous_status
            context.loop_state.current_task = previous_task
            self.workspace.save_project(context)
    def _run_merger_pass(
        self,
        *,
        context: ProjectContext,
        runner: CodexRunner,
        reporter: Reporter,
        block_index: int,
        candidate: CandidateTask,
        execution_step: ExecutionStep | None,
        memory_context: str,
        failing_command: str,
        failing_summary: str,
        failing_stdout: str,
        failing_stderr: str,
        merge_targets: list[str] | None = None,
        post_success_strategy: str = "continue_cherry_pick",
    ) -> tuple[str, object, bool, str | None]:
        merge_pass_name = self._merge_pass_name(failing_command)
        merger_prompt_template = load_merger_prompt_template(context.runtime.execution_mode)
        previous_status = context.metadata.current_status
        previous_task = context.loop_state.current_task
        context.metadata.current_status = "running:merging"
        context.metadata.last_run_at = now_utc_iso()
        context.loop_state.current_task = f"Merging {candidate.title}".strip()
        self.workspace.save_project(context)
        prompt = merger_prompt(
            context=context,
            candidate=candidate,
            memory_context=memory_context,
            failing_command=failing_command,
            failing_summary=failing_summary,
            failing_stdout=failing_stdout,
            failing_stderr=failing_stderr,
            merge_targets=merge_targets,
            execution_step=execution_step,
            template_text=merger_prompt_template,
        )
        try:
            run_result = self._run_pass_with_provider_fallback(
                context=context,
                runner=runner,
                prompt=prompt,
                pass_type=merge_pass_name,
                block_index=block_index,
                search_enabled=False,
                execution_step=execution_step,
            )
            run_result.changed_files = self.git.changed_files(context.paths.repo_dir)
            if run_result.returncode != 0:
                return merge_pass_name, run_result, False, None
            if self.git.conflicted_files(context.paths.repo_dir):
                return merge_pass_name, run_result, False, None

            commit_hash: str | None = None
            commit_descriptor = build_commit_descriptor(
                context,
                merge_pass_name,
                candidate.title,
                execution_step=execution_step,
            )
            if post_success_strategy == "continue_cherry_pick":
                if self.git.cherry_pick_in_progress(context.paths.repo_dir):
                    self.git.add_all(context.paths.repo_dir)
                    commit_hash = self.git.commit_staged(
                        context.paths.repo_dir,
                        commit_descriptor.message,
                        author_name=commit_descriptor.author_name,
                    )
                elif self.git.has_changes(context.paths.repo_dir):
                    commit_hash = self.git.commit_all(
                        context.paths.repo_dir,
                        commit_descriptor.message,
                        author_name=commit_descriptor.author_name,
                    )
                else:
                    commit_hash = self.git.current_revision(context.paths.repo_dir)
            elif post_success_strategy == "commit_if_changes":
                if self.git.has_changes(context.paths.repo_dir):
                    commit_hash = self.git.commit_all(
                        context.paths.repo_dir,
                        commit_descriptor.message,
                        author_name=commit_descriptor.author_name,
                    )
                else:
                    commit_hash = self.git.current_revision(context.paths.repo_dir)
            else:
                raise ValueError(f"Unsupported merger success strategy: {post_success_strategy}")
            return merge_pass_name, run_result, True, commit_hash
        finally:
            context.metadata.last_run_at = now_utc_iso()
            if context.metadata.current_status == "running:merging":
                context.metadata.current_status = previous_status
            context.loop_state.current_task = previous_task
            self.workspace.save_project(context)
    def _build_parallel_batch_debug_step(
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
        return ExecutionStep(
            step_id="BATCH",
            title=f"Recover merged parallel batch {titles}",
            display_description=f"Repair merged verification failures for {titles}.",
            codex_description=(
                "Inspect the merged batch failure, use the provided verification logs, and repair the implementation so the "
                "batch passes without broad refactors or unnecessary test changes."
            ),
            test_command=test_command,
            success_criteria=f"The verification command `{test_command}` exits successfully for the merged batch.",
            reasoning_effort="high",
            depends_on=step_ids,
            owned_paths=ordered_paths,
            metadata={"parallel_step_titles": parallel_step_titles},
        )
    def _latest_failure_bundle_json(self, context: ProjectContext) -> dict[str, object]:
        latest_failure_status = read_json(context.paths.reports_dir / "latest_pr_failure_status.json", default={})
        if not isinstance(latest_failure_status, dict) or not latest_failure_status:
            return {}
        report_json_file = str(latest_failure_status.get("report_json_file", "")).strip()
        if not report_json_file:
            return {}
        bundle_json = read_json(Path(report_json_file), default={})
        return bundle_json if isinstance(bundle_json, dict) else {}
    def _latest_failed_test_run_entry(
        self,
        context: ProjectContext,
        *,
        preferred_labels: tuple[str, ...] = (),
    ) -> dict[str, object] | None:
        recent_test_runs = read_jsonl_tail(context.paths.logs_dir / "test_runs.jsonl", 40)
        normalized_preferred = tuple(str(item).strip().lower() for item in preferred_labels if str(item).strip())
        for entry in reversed(recent_test_runs):
            try:
                returncode = int(entry.get("returncode", 0))
            except (TypeError, ValueError):
                continue
            if returncode == 0:
                continue
            label = str(entry.get("label", "")).strip().lower()
            if normalized_preferred and label not in normalized_preferred:
                continue
            return entry
        return None
    def _test_run_result_from_log_entry(self, context: ProjectContext, entry: dict[str, object]) -> TestRunResult:
        label = str(entry.get("label", "")).strip() or "manual-recovery"
        stdout_file_value = str(entry.get("stdout_file", "")).strip()
        stderr_file_value = str(entry.get("stderr_file", "")).strip()
        stdout_file = Path(stdout_file_value) if stdout_file_value else context.paths.logs_dir / f"{label}.stdout.log"
        stderr_file = Path(stderr_file_value) if stderr_file_value else context.paths.logs_dir / f"{label}.stderr.log"
        try:
            returncode = int(entry.get("returncode", 1))
        except (TypeError, ValueError):
            returncode = 1
        return TestRunResult(
            command=str(entry.get("command", context.runtime.test_cmd)).strip() or context.runtime.test_cmd,
            returncode=returncode,
            stdout_file=stdout_file,
            stderr_file=stderr_file,
            summary=str(entry.get("summary", "")).strip() or f"{label} failed.",
            failure_reason=str(entry.get("failure_reason", "")).strip(),
            duration_seconds=float(entry.get("duration_seconds", 0.0) or 0.0),
            source_duration_seconds=float(entry.get("source_duration_seconds", 0.0) or 0.0),
            cache_hit=bool(entry.get("cache_hit")),
            state_fingerprint=str(entry.get("state_fingerprint", "")).strip() or None,
            cache_key=str(entry.get("cache_key", "")).strip() or None,
        )
    def _latest_failed_pass_entry(
        self,
        context: ProjectContext,
        bundle_json: dict[str, object],
    ) -> dict[str, object] | None:
        recent_passes = bundle_json.get("recent_passes", []) if isinstance(bundle_json, dict) else []
        for entry in reversed(recent_passes if isinstance(recent_passes, list) else []):
            if not isinstance(entry, dict):
                continue
            try:
                returncode = int(entry.get("codex_return_code", entry.get("returncode", 0)))
            except (TypeError, ValueError):
                continue
            if returncode != 0:
                return entry
        for entry in reversed(read_jsonl_tail(context.paths.pass_log_file, 40)):
            if not isinstance(entry, dict):
                continue
            try:
                returncode = int(entry.get("codex_return_code", entry.get("returncode", 0)))
            except (TypeError, ValueError):
                continue
            if returncode != 0:
                return entry
        return None

    def _pass_artifact_sort_key(self, path: Path, *, pass_name: str) -> tuple[int, int, str]:
        attempt_index = 0
        stem = path.name
        prefix = f"{pass_name}.attempt_"
        if stem.startswith(prefix):
            remainder = stem[len(prefix) :]
            attempt_text = remainder.split(".", 1)[0]
            try:
                attempt_index = int(attempt_text)
            except (TypeError, ValueError):
                attempt_index = 0
        try:
            mtime_ns = int(path.stat().st_mtime_ns)
        except OSError:
            mtime_ns = 0
        return (mtime_ns, attempt_index, stem)

    def _pass_artifact_path(self, block_dir: Path, pass_name: str, suffix: str) -> Path | None:
        candidates = [block_dir / f"{pass_name}{suffix}"]
        candidates.extend(block_dir.glob(f"{pass_name}.attempt_*{suffix}"))
        existing_candidates = [candidate for candidate in candidates if candidate.exists()]
        if not existing_candidates:
            return None
        return max(existing_candidates, key=lambda candidate: self._pass_artifact_sort_key(candidate, pass_name=pass_name))
    def _test_run_result_from_pass_entry(
        self,
        context: ProjectContext,
        bundle_json: dict[str, object],
        entry: dict[str, object],
    ) -> tuple[TestRunResult, str]:
        pass_name = str(entry.get("pass_type", entry.get("label", ""))).strip() or "manual-debugger"
        block_index = self._manual_recovery_block_index(context, bundle_json=bundle_json, test_entry=entry)
        block_dir = ensure_dir(context.paths.logs_dir / f"block_{block_index:04d}")
        event_file = self._pass_artifact_path(block_dir, pass_name, ".events.jsonl")
        stderr_file = self._pass_artifact_path(block_dir, pass_name, ".stderr.log")
        output_file = self._pass_artifact_path(block_dir, pass_name, ".last_message.txt")
        try:
            returncode = int(entry.get("codex_return_code", entry.get("returncode", 1)))
        except (TypeError, ValueError):
            returncode = 1
        diagnostics = entry.get("codex_diagnostics", {})
        synthetic_run_result = CodexRunResult(
            pass_type=pass_name,
            prompt_file=block_dir / f"{pass_name}.prompt.md",
            output_file=output_file or (block_dir / f"{pass_name}.last_message.txt"),
            event_file=event_file or (block_dir / f"{pass_name}.events.jsonl"),
            returncode=returncode,
            search_enabled=bool(entry.get("search_enabled")),
            changed_files=[],
            usage=entry.get("usage", {}) if isinstance(entry.get("usage", {}), dict) else {},
            last_message=read_text(output_file).strip() if isinstance(output_file, Path) and output_file.exists() else None,
            attempt_count=int(entry.get("codex_attempt_count", 1) or 1),
            duration_seconds=float(entry.get("duration_seconds", 0.0) or 0.0),
            diagnostics=diagnostics if isinstance(diagnostics, dict) else {},
        )
        detail = self._run_result_failure_detail(synthetic_run_result)
        summary = str(bundle_json.get("summary", "")).strip()
        if detail and detail not in summary:
            summary = f"{summary} Cause: {detail}".strip() if summary else f"Codex execution failed before verification. Cause: {detail}"
        if not summary:
            summary = f"{pass_name} failed before verification."
        stdout_target = block_dir / f"{pass_name}.manual_debugger.stdout.log"
        stderr_target = block_dir / f"{pass_name}.manual_debugger.stderr.log"
        stdout_text = read_text(event_file) if isinstance(event_file, Path) and event_file.exists() else ""
        stderr_text = read_text(stderr_file) if isinstance(stderr_file, Path) and stderr_file.exists() else ""
        attempts = synthetic_run_result.diagnostics.get("attempts", []) if isinstance(synthetic_run_result.diagnostics, dict) else []
        if not stdout_text:
            for attempt in reversed(attempts if isinstance(attempts, list) else []):
                if not isinstance(attempt, dict):
                    continue
                stdout_text = str(attempt.get("stdout_excerpt", "") or "").strip()
                if stdout_text:
                    break
        if not stderr_text:
            for attempt in reversed(attempts if isinstance(attempts, list) else []):
                if not isinstance(attempt, dict):
                    continue
                stderr_text = str(attempt.get("stderr_excerpt", "") or "").strip()
                if stderr_text:
                    break
        write_text(stdout_target, stdout_text or summary)
        write_text(stderr_target, stderr_text or detail or summary)
        return (
            TestRunResult(
                command=pass_name,
                returncode=max(1, returncode),
                stdout_file=stdout_target,
                stderr_file=stderr_target,
                summary=summary,
                failure_reason=detail,
                duration_seconds=float(entry.get("duration_seconds", 0.0) or 0.0),
            ),
            pass_name,
        )
    def _manual_recovery_block_index(
        self,
        context: ProjectContext,
        *,
        bundle_json: dict[str, object],
        test_entry: dict[str, object] | None = None,
    ) -> int:
        raw_block_index = bundle_json.get("block_index") if isinstance(bundle_json, dict) else None
        if raw_block_index is None and isinstance(test_entry, dict):
            raw_block_index = test_entry.get("block_index")
        try:
            block_index = int(raw_block_index)
        except (TypeError, ValueError):
            block_index = int(context.loop_state.block_index or 0)
        return max(1, block_index)
    def _manual_recovery_steps(
        self,
        plan_state: ExecutionPlanState,
        *,
        selected_task: str,
        failing_label: str,
    ) -> list[ExecutionStep]:
        normalized_task = str(selected_task).strip().lower()
        normalized_label = str(failing_label).strip().lower()
        for step in plan_state.steps:
            if normalized_task and normalized_task in {step.step_id.strip().lower(), step.title.strip().lower()}:
                return [step]
        failed_steps = [step for step in plan_state.steps if step.status == "failed"]
        if normalized_label.startswith("parallel-batch") or "parallel batch" in normalized_task:
            if len(failed_steps) >= 2:
                return failed_steps
            non_completed = [step for step in plan_state.steps if step.status != "completed"]
            return non_completed if non_completed else failed_steps
        if failed_steps:
            return failed_steps
        return []
    def _manual_debugger_failure_message(self, run_result, test_result: TestRunResult | None) -> str:
        if test_result is not None and test_result.returncode != 0:
            return str(test_result.summary).strip() or "Manual debugger recovery still failed verification."
        message = str(getattr(run_result, "last_message", "") or "").strip()
        if message:
            return message
        if isinstance(run_result, CodexRunResult):
            detail = self._run_result_failure_detail(run_result)
            if detail:
                return detail
        return f"Manual debugger pass failed with code {int(getattr(run_result, 'returncode', 1) or 1)}."
    def _manual_merger_failure_message(self, run_result, success: bool) -> str:
        if success:
            return ""
        message = str(getattr(run_result, "last_message", "") or "").strip()
        if message:
            return message
        return f"Manual merger pass failed with code {int(getattr(run_result, 'returncode', 1) or 1)}."
    def run_manual_debugger_recovery(
        self,
        project_dir: Path,
        runtime: RuntimeOptions,
        branch: str = "main",
        origin_url: str = "",
    ) -> tuple[ProjectContext, ExecutionPlanState, dict[str, object]]:
        context = self.setup_local_project(project_dir=project_dir, runtime=runtime, branch=branch, origin_url=origin_url)
        plan_state = self.load_execution_plan_state(context)
        bundle_json = self._latest_failure_bundle_json(context)
        failing_test_entry = self._latest_failed_test_run_entry(context)
        failing_pass_name = "manual-debugger"
        if failing_test_entry is not None:
            failing_test_result = self._test_run_result_from_log_entry(context, failing_test_entry)
            failing_pass_name = str(failing_test_entry.get("label", "")).strip() or failing_pass_name
        else:
            failing_pass_entry = self._latest_failed_pass_entry(context, bundle_json)
            if failing_pass_entry is None:
                raise MissingRecoveryArtifactsError(
                    "No failed verification log or Codex pass diagnostics are available for manual debugger recovery."
                )
            failing_test_result, failing_pass_name = self._test_run_result_from_pass_entry(context, bundle_json, failing_pass_entry)
        selected_task = str(bundle_json.get("selected_task", "")).strip()
        recovery_steps = self._manual_recovery_steps(
            plan_state,
            selected_task=selected_task,
            failing_label=failing_pass_name,
        )
        test_command = str(plan_state.default_test_command or runtime.test_cmd).strip() or runtime.test_cmd
        execution_step: ExecutionStep | None = None
        if len(recovery_steps) > 1 or str(failing_pass_name).strip().lower().startswith("parallel-batch"):
            execution_step = self._build_parallel_batch_debug_step(recovery_steps, test_command)
        elif recovery_steps:
            execution_step = recovery_steps[0]
        candidate_title = selected_task or (execution_step.title if execution_step is not None else "Manual debugger recovery")
        candidate = CandidateTask(
            candidate_id="manual-debugger",
            title=candidate_title,
            rationale=(
                self._execution_step_rationale(execution_step, test_command)
                if execution_step is not None
                else "Inspect the latest failing verification logs and repair the current repository state safely."
            ),
            plan_refs=[step.step_id for step in recovery_steps],
            score=1.0,
        )
        runner = CodexRunner(context.runtime.codex_path)
        reporter = Reporter(context)
        memory_context = MemoryStore(context.paths).render_context(read_text(context.paths.mid_term_plan_file))
        block_index = self._manual_recovery_block_index(
            context,
            bundle_json=bundle_json,
            test_entry=failing_test_entry,
        )
        pass_name, run_result, test_result, commit_hash = self._run_debugger_pass(
            context=context,
            runner=runner,
            reporter=reporter,
            block_index=block_index,
            candidate=candidate,
            execution_step=execution_step,
            memory_context=memory_context,
            failing_pass_name=failing_pass_name,
            failing_test_result=failing_test_result,
        )
        failure_summary = self._manual_debugger_failure_message(run_result, test_result)
        if run_result.returncode != 0 or test_result is None or test_result.returncode != 0:
            failure = (
                AgentPassExecutionError(failure_summary)
                if run_result.returncode != 0 or test_result is None
                else VerificationTestFailure(failure_summary)
            )
            rollback_status = "manual_recovery_failed"
            self._log_pass_result(
                context=context,
                reporter=reporter,
                block_index=block_index,
                candidate=candidate,
                pass_name=pass_name,
                run_result=run_result,
                test_result=test_result,
                commit_hash=None,
                rollback_status=rollback_status,
                search_enabled=False,
            )
            self._report_failure(
                context,
                reporter,
                failure_type="manual_debugger_failed",
                summary=failure_summary,
                block_index=block_index,
                selected_task=candidate.title,
                extra={
                    "artifact_paths": [
                        str(failing_test_result.stdout_file),
                        str(failing_test_result.stderr_file),
                    ],
                },
            )
            latest_failure_status = read_json(context.paths.reports_dir / "latest_pr_failure_status.json", default={})
            failure_report = str(latest_failure_status.get("report_markdown_file", "")).strip() if isinstance(latest_failure_status, dict) else ""
            if failure_report:
                raise type(failure)(f"{failure_summary} Failure report: {failure_report}")
            raise failure
        self._log_pass_result(
            context=context,
            reporter=reporter,
            block_index=block_index,
            candidate=candidate,
            pass_name=pass_name,
            run_result=run_result,
            test_result=test_result,
            commit_hash=commit_hash,
            rollback_status="not_needed",
            search_enabled=False,
        )
        if commit_hash:
            context.metadata.current_safe_revision = commit_hash
            context.loop_state.current_safe_revision = commit_hash
            context.loop_state.last_commit_hash = commit_hash
            context.metadata.last_run_at = now_utc_iso()
            self.workspace.save_project(context)
        self.clear_latest_failure_status(context)
        reporter.write_status_report()
        return context, self.load_execution_plan_state(context), {
            "pass_name": pass_name,
            "summary": str(test_result.summary).strip(),
            "commit_hash": commit_hash,
        }
    def run_manual_merger_recovery(
        self,
        project_dir: Path,
        runtime: RuntimeOptions,
        branch: str = "main",
        origin_url: str = "",
    ) -> tuple[ProjectContext, ExecutionPlanState, dict[str, object]]:
        context = self.setup_local_project(project_dir=project_dir, runtime=runtime, branch=branch, origin_url=origin_url)
        plan_state = self.load_execution_plan_state(context)
        conflicted_files = self.git.conflicted_files(context.paths.repo_dir)
        if not conflicted_files:
            raise MergeConflictStateError("No active git conflict is available for manual merger recovery.")

        bundle_json = self._latest_failure_bundle_json(context)
        selected_task = str(bundle_json.get("selected_task", "")).strip()
        recovery_steps = self._manual_recovery_steps(
            plan_state,
            selected_task=selected_task,
            failing_label="parallel-batch-merge",
        )
        test_command = str(plan_state.default_test_command or runtime.test_cmd).strip() or runtime.test_cmd
        execution_step = self._build_parallel_batch_merge_step(recovery_steps, test_command)
        candidate = CandidateTask(
            candidate_id="manual-merger",
            title=selected_task or execution_step.title,
            rationale=self._execution_step_rationale(execution_step, test_command),
            plan_refs=[step.step_id for step in recovery_steps],
            score=1.0,
        )
        runner = CodexRunner(context.runtime.codex_path)
        reporter = Reporter(context)
        memory_context = MemoryStore(context.paths).render_context(read_text(context.paths.mid_term_plan_file))
        block_index = self._manual_recovery_block_index(context, bundle_json=bundle_json)
        git_status_result = self.git.run(["status", "--short"], cwd=context.paths.repo_dir, check=False)
        report_text = ""
        report_markdown_file = str(bundle_json.get("report_markdown_file", "")).strip()
        if report_markdown_file:
            report_text = read_text(Path(report_markdown_file))
        failing_summary = (
            str(bundle_json.get("summary", "")).strip()
            or f"Manual merge recovery requested for conflicted files: {', '.join(conflicted_files)}."
        )
        pass_name, run_result, success, commit_hash = self._run_merger_pass(
            context=context,
            runner=runner,
            reporter=reporter,
            block_index=block_index,
            candidate=candidate,
            execution_step=execution_step,
            memory_context=memory_context,
            failing_command="parallel-batch-merge",
            failing_summary=failing_summary,
            failing_stdout=git_status_result.stdout,
            failing_stderr=report_text or git_status_result.stderr or failing_summary,
            merge_targets=[step.step_id for step in recovery_steps],
            post_success_strategy="continue_cherry_pick",
        )
        failure_summary = self._manual_merger_failure_message(run_result, success)
        if run_result.returncode != 0 or not success:
            failure = AgentPassExecutionError(failure_summary) if run_result.returncode != 0 else ParallelMergeConflictError(failure_summary)
            rollback_status = "manual_recovery_failed"
            self._log_pass_result(
                context=context,
                reporter=reporter,
                block_index=block_index,
                candidate=candidate,
                pass_name=pass_name,
                run_result=run_result,
                test_result=None,
                commit_hash=None,
                rollback_status=rollback_status,
                search_enabled=False,
            )
            self._report_failure(
                context,
                reporter,
                failure_type="manual_merger_failed",
                summary=failure_summary,
                block_index=block_index,
                selected_task=candidate.title,
                extra={"conflict": self._parallel_conflict_details(conflicted_files)},
            )
            latest_failure_status = read_json(context.paths.reports_dir / "latest_pr_failure_status.json", default={})
            failure_report = str(latest_failure_status.get("report_markdown_file", "")).strip() if isinstance(latest_failure_status, dict) else ""
            if failure_report:
                raise type(failure)(f"{failure_summary} Failure report: {failure_report}")
            raise failure
        self._log_pass_result(
            context=context,
            reporter=reporter,
            block_index=block_index,
            candidate=candidate,
            pass_name=pass_name,
            run_result=run_result,
            test_result=None,
            commit_hash=commit_hash,
            rollback_status="not_needed",
            search_enabled=False,
        )
        if commit_hash:
            context.metadata.current_safe_revision = commit_hash
            context.loop_state.current_safe_revision = commit_hash
            context.loop_state.last_commit_hash = commit_hash
            context.metadata.last_run_at = now_utc_iso()
            self.workspace.save_project(context)
        self.clear_latest_failure_status(context)
        reporter.write_status_report()
        return context, self.load_execution_plan_state(context), {
            "pass_name": pass_name,
            "summary": f"Resolved conflicted files: {', '.join(conflicted_files)}.",
            "commit_hash": commit_hash,
        }
