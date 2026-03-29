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
from .execution_control import ImmediateStopRequested
from .git_ops import GitOps
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
from .orchestrator_lineage import OrchestratorLineageMixin
from .orchestrator_ml import OrchestratorMlMixin
from .orchestrator_recovery import OrchestratorRecoveryMixin

UTC = getattr(datetime, "UTC", timezone.utc)


class Orchestrator(OrchestratorLineageMixin, OrchestratorMlMixin, OrchestratorRecoveryMixin):
    _STALE_CLOSEOUT_TIMEOUT = timedelta(hours=6)

    def __init__(self, workspace_root: Path) -> None:
        self.workspace = WorkspaceManager(workspace_root)
        self.git = GitOps()
        self.verification = VerificationRunner()

    def setup_local_project(
        self,
        project_dir: Path,
        runtime: RuntimeOptions,
        branch: str = "main",
        origin_url: str = "",
        display_name: str = "",
    ) -> ProjectContext:
        runtime.execution_mode = self._normalize_execution_mode(runtime.execution_mode)
        resolved_dir = project_dir.resolve()
        created_repo = self.git.ensure_repository(resolved_dir, branch)
        active_branch = self.git.current_branch(resolved_dir) or branch or "main"
        if origin_url.strip():
            self.git.set_remote_url(resolved_dir, "origin", origin_url.strip())
        detected_origin = self.git.remote_url(resolved_dir, "origin")

        existing = self.workspace.find_project_by_repo_path(resolved_dir)
        if existing is None:
            context = self.workspace.initialize_local_project(
                project_dir=resolved_dir,
                branch=active_branch,
                runtime=runtime,
                origin_url=detected_origin or origin_url.strip(),
                display_name=display_name.strip(),
            )
        else:
            context = existing
            context.runtime = runtime
            context.metadata.branch = active_branch
            context.metadata.repo_path = resolved_dir
            context.metadata.repo_url = detected_origin or origin_url.strip() or str(resolved_dir)
            context.metadata.origin_url = detected_origin or origin_url.strip() or None
            context.metadata.repo_kind = "local"
            context.metadata.display_name = display_name.strip() or context.metadata.display_name or resolved_dir.name

        self.git.configure_local_identity(
            context.paths.repo_dir,
            runtime.git_user_name,
            runtime.git_user_email,
        )
        ensure_virtualenv(context.paths.repo_dir)
        ensure_gitignore(context.paths.repo_dir)
        self._ensure_project_documents(context)

        if created_repo or not self.git.has_commits(context.paths.repo_dir):
            initial_commit = build_initial_commit_descriptor(context)
            safe_revision = self.git.create_initial_commit(
                context.paths.repo_dir,
                initial_commit.message,
                author_name=initial_commit.author_name,
            )
        else:
            safe_revision = self.git.current_revision(context.paths.repo_dir)

        context.metadata.branch = self.git.current_branch(context.paths.repo_dir) or active_branch
        context.metadata.current_safe_revision = safe_revision
        context.metadata.current_status = "setup_ready"
        context.metadata.last_run_at = now_utc_iso()
        context.metadata.repo_url = self.git.remote_url(context.paths.repo_dir, "origin") or str(context.paths.repo_dir)
        context.metadata.origin_url = self.git.remote_url(context.paths.repo_dir, "origin")
        context.metadata.repo_kind = "local"
        context.metadata.display_name = display_name.strip() or context.metadata.display_name or context.paths.repo_dir.name
        context.loop_state.current_safe_revision = safe_revision
        context.loop_state.stop_requested = False
        context.loop_state.stop_reason = None
        self._clear_stale_checkpoint_approval_state(context)
        self.workspace.save_project(context)
        self.save_execution_plan_state(context, self.load_execution_plan_state(context))
        return context

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
        project_prompt = project_prompt.strip()
        previous_plan_state = self.load_execution_plan_state(context)
        workflow_mode = normalize_workflow_mode(runtime.workflow_mode)
        normalized_execution_mode = self._normalize_execution_mode(runtime.execution_mode)
        planning_effort = normalize_reasoning_effort(
            getattr(runtime, "planning_effort", ""),
            fallback=normalize_reasoning_effort(runtime.effort, fallback="high"),
        )
        planning_effort = self._planning_effort_for_runtime(runtime, planning_effort)
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
        repo_inputs = scan_repository_inputs(context.paths.repo_dir)
        runner = CodexRunner(context.runtime.codex_path)
        skip_planner_a = self._should_skip_planner_decomposition(context, planning_effort, workflow_mode)
        planner_outline = ""
        if skip_planner_a:
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
            planner_outline = build_fast_planner_outline(repo_inputs, project_prompt)
            report_progress(
                "planner-agent-finished",
                "Planner Agent A was skipped in fast mode; a compact heuristic outline was saved instead.",
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
        prompt = prompt_to_execution_plan_prompt(
            context=context,
            repo_inputs=repo_inputs,
            user_prompt=project_prompt,
            max_steps=max_steps,
            execution_mode=normalized_execution_mode,
            planner_outline=planner_outline,
            template_text=planning_prompt_template,
        )
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
        plan_title = ""
        summary = ""
        steps: list[ExecutionStep] = []
        if result.returncode == 0:
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
        self.save_execution_plan_state(context, plan_state)
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
        context: ProjectContext,
        planning_effort: str,
        workflow_mode: str,
    ) -> bool:
        if workflow_mode == "ml":
            return False
        if planning_effort == "xhigh":
            return False
        return bool(getattr(context.runtime, "use_fast_mode", False))

    def _planning_effort_for_runtime(self, runtime: RuntimeOptions, planning_effort: str) -> str:
        selected_provider = str(getattr(runtime, "model_provider", "") or "").strip().lower()
        if selected_provider == "ensemble":
            planning_model = str(getattr(runtime, "ensemble_openai_model", "") or getattr(runtime, "model", "")).strip().lower()
        else:
            planning_model = str(getattr(runtime, "model", "") or getattr(runtime, "model_slug_input", "")).strip().lower()
        normalized_effort = normalize_reasoning_effort(planning_effort, fallback="high")
        if planning_model != "gpt-5.4":
            return normalized_effort
        effort_ladder = ["low", "medium", "high", "xhigh"]
        current_index = effort_ladder.index(normalized_effort) if normalized_effort in effort_ladder else 1
        return effort_ladder[max(0, current_index - 1)]

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
        payload = read_json(context.paths.execution_plan_file, default=None)
        if not isinstance(payload, dict):
            return ExecutionPlanState(
                workflow_mode=normalize_workflow_mode(context.runtime.workflow_mode),
                default_test_command=context.runtime.test_cmd,
                last_updated_at=now_utc_iso(),
                steps=[],
            )
        state = ExecutionPlanState.from_dict(payload)
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
        self._recover_stale_closeout_state(context, state)
        return state

    def _stale_closeout_note(self, context: ProjectContext, plan_state: ExecutionPlanState) -> str:
        note_parts = [
            "Closeout appears to have stopped before it finished; the saved running state was recovered as failed."
        ]
        started_at = str(plan_state.closeout_started_at or "").strip()
        if started_at:
            note_parts.append(f"Started at {started_at}.")
        latest_failure_status = read_json(context.paths.reports_dir / "latest_pr_failure_status.json", default={})
        if isinstance(latest_failure_status, dict):
            report_path = str(latest_failure_status.get("report_markdown_file", "")).strip()
            if report_path:
                note_parts.append(f"Latest failure report: {report_path}")
        existing_notes = str(plan_state.closeout_notes or "").strip()
        if existing_notes and existing_notes not in note_parts:
            note_parts.append(existing_notes)
        return " ".join(note_parts).strip()

    def _recover_stale_closeout_state(self, context: ProjectContext, plan_state: ExecutionPlanState) -> bool:
        if not self._closeout_run_is_stale(context, plan_state):
            return False
        plan_state.closeout_status = "failed"
        plan_state.closeout_completed_at = None
        plan_state.closeout_commit_hash = None
        plan_state.closeout_notes = self._stale_closeout_note(context, plan_state)
        plan_state.last_updated_at = now_utc_iso()
        write_json(context.paths.execution_plan_file, plan_state.to_dict())
        context.metadata.current_status = self._status_from_plan_state(plan_state)
        context.metadata.last_run_at = plan_state.last_updated_at
        self.workspace.save_project(context)
        return True

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
        execution_mode = self._normalize_execution_mode(plan_state.execution_mode or context.runtime.execution_mode)
        workflow_mode = normalize_workflow_mode(plan_state.workflow_mode or context.runtime.workflow_mode)
        normalized_steps = self._normalize_execution_steps(context, plan_state.steps, plan_state.default_test_command, execution_mode)
        closeout_ready = self._all_steps_completed(normalized_steps)
        closeout_status = plan_state.closeout_status.strip() or "not_started"
        closeout_started_at = plan_state.closeout_started_at
        closeout_completed_at = plan_state.closeout_completed_at
        closeout_commit_hash = plan_state.closeout_commit_hash
        closeout_notes = plan_state.closeout_notes.strip()
        if not closeout_ready:
            closeout_status = "not_started"
            closeout_started_at = None
            closeout_completed_at = None
            closeout_commit_hash = None
            closeout_notes = ""
        state = ExecutionPlanState(
            plan_title=plan_state.plan_title.strip() or context.metadata.display_name or context.metadata.slug,
            project_prompt=plan_state.project_prompt.strip(),
            summary=plan_state.summary.strip(),
            workflow_mode=workflow_mode,
            execution_mode=execution_mode,
            default_test_command=plan_state.default_test_command.strip() or context.runtime.test_cmd,
            last_updated_at=now_utc_iso(),
            closeout_status=closeout_status,
            closeout_started_at=closeout_started_at,
            closeout_completed_at=closeout_completed_at,
            closeout_commit_hash=closeout_commit_hash,
            closeout_notes=closeout_notes,
            steps=normalized_steps,
        )
        write_json(context.paths.execution_plan_file, state.to_dict())
        write_text(
            context.paths.plan_file,
            execution_plan_markdown(context, state.plan_title, state.project_prompt, state.summary, state.workflow_mode, state.execution_mode, state.steps),
        )
        mid_term_text, _ = build_mid_term_plan_from_plan_items(
            execution_steps_to_plan_items(state.steps),
            "This plan is the user-reviewed execution sequence for the current local project.",
        )
        write_text(context.paths.mid_term_plan_file, mid_term_text)
        write_text(context.paths.scope_guard_file, ensure_scope_guard(context))
        checkpoints = self._checkpoints_from_execution_steps(state.steps)
        write_json(context.paths.checkpoint_state_file, {"checkpoints": [checkpoint.to_dict() for checkpoint in checkpoints]})
        write_text(context.paths.checkpoint_timeline_file, checkpoint_timeline_markdown(checkpoints))
        flow_title = state.plan_title or context.metadata.display_name or context.metadata.slug
        write_text(context.paths.execution_flow_svg_file, execution_plan_svg(f"{flow_title} execution flow", state.steps, state.execution_mode))
        return state

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
            normalized_steps.append(
                ExecutionStep(
                    step_id=id_map[raw_id],
                    title=step.title.strip(),
                    display_description=step.display_description.strip(),
                    codex_description=step.codex_description.strip() or step.display_description.strip() or step.title.strip(),
                    deadline_at=step.deadline_at.strip(),
                    model_provider=normalize_step_model_provider(step.model_provider),
                    model=normalize_step_model(step.model),
                    test_command=step.test_command.strip() or default_test_command or context.runtime.test_cmd,
                    success_criteria=step.success_criteria.strip(),
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
        execution_plan_support.reduce_redundant_parallel_dependencies(steps)

    def _plan_uses_dag_parallelism(self, steps: list[ExecutionStep]) -> bool:
        return execution_plan_support.plan_uses_dag_parallelism(steps)

    def _validate_hybrid_execution_steps(self, steps: list[ExecutionStep]) -> None:
        step_ids = {step.step_id for step in steps}
        for step in steps:
            step_kind = self._step_kind(step)
            metadata = step.metadata if isinstance(step.metadata, dict) else {}
            if step_kind in {"join", "barrier"} and step.parallel_group.strip():
                raise ValueError(f"{step.step_id} cannot use parallel_group because {step_kind} steps run alone.")
            if step_kind == "join":
                if len(step.depends_on) < 2:
                    raise ValueError(f"{step.step_id} must depend on at least two prior steps to act as a join node.")
                merge_from = self._coerce_string_list(metadata.get("merge_from", []))
                if len(merge_from) < 2:
                    raise ValueError(f"{step.step_id} must declare at least two merge_from step ids.")
                unknown_merge_targets = [item for item in merge_from if item not in step_ids]
                if unknown_merge_targets:
                    raise ValueError(f"{step.step_id} references unknown join targets: {', '.join(unknown_merge_targets)}")
                invalid_merge_targets = [item for item in merge_from if item not in step.depends_on]
                if invalid_merge_targets:
                    raise ValueError(
                        f"{step.step_id} can only merge direct dependencies, but merge_from included: {', '.join(invalid_merge_targets)}"
                    )
                join_policy = self._normalize_join_policy(metadata.get("join_policy", ""))
                if join_policy != "all":
                    raise ValueError(f"{step.step_id} uses unsupported join_policy '{join_policy}'. Only 'all' is supported.")
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
            for step in plan_state.steps:
                if step.step_id == target_step.step_id:
                    step.status = "failed"
                    step.completed_at = None
                    step.commit_hash = None
                    step.notes = preflight_error
                elif step.status == "running":
                    step.status = "paused"
            context.loop_state.stop_reason = preflight_error
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
                context.metadata.current_status = self._status_from_plan_state(plan_state)
            else:
                target_step.status = "failed"
                failure_summary = ""
                if latest_block:
                    failure_summary = str(latest_block.get("test_summary", "")).strip()
                if not failure_summary:
                    failure_summary = str(context.loop_state.stop_reason or f"Step execution failed after {attempt_count} attempt(s).").strip()
                target_step.notes = failure_summary or "Step execution failed."
                context.metadata.current_status = "failed"
            self._collect_ml_step_report(context, target_step)
        except ImmediateStopRequested as exc:
            self.git.hard_reset(context.paths.repo_dir, context.metadata.current_safe_revision or self.git.current_revision(context.paths.repo_dir))
            target_step.status = "paused"
            target_step.completed_at = None
            target_step.commit_hash = None
            target_step.notes = str(exc).strip() or "Immediate stop requested."
            context.metadata.current_status = self._status_from_plan_state(plan_state)
        except Exception as exc:
            target_step.status = "failed"
            target_step.notes = str(exc).strip() or "Step execution failed."
            self._collect_ml_step_report(context, target_step)
            context.metadata.current_status = "failed"
            raise
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
        context = self.setup_local_project(project_dir=project_dir, runtime=runtime, branch=branch, origin_url=origin_url)
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
        latest_block: dict[str, object] | None = None
        attempts = 0
        while attempts < attempt_limit:
            attempts += 1
            previous_block = read_last_jsonl(context.paths.block_log_file)
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
            latest_block = read_last_jsonl(context.paths.block_log_file)
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
        context = self.setup_local_project(project_dir=project_dir, runtime=runtime, branch=branch, origin_url=origin_url)
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
                        merge_result = self.git.try_cherry_pick(context.paths.repo_dir, worker_commit)
                        if merge_result.returncode == 0:
                            merged_commit = self.git.current_revision(context.paths.repo_dir)
                            merged_commit_hashes.append(merged_commit)
                            merged_commit_by_step_id[result_step_id] = merged_commit
                            continue
                        conflicted_files = self.git.conflicted_files(context.paths.repo_dir)
                        failure_extra = {"conflict": self._parallel_conflict_details(conflicted_files)}
                        if conflicted_files and self.git.cherry_pick_in_progress(context.paths.repo_dir):
                            merge_test_result = self._parallel_merge_conflict_test_result(
                                context=context,
                                worker_commit=worker_commit,
                                merge_result=merge_result,
                                conflicted_files=conflicted_files,
                            )
                            merge_pass_name, merge_run_result, merge_success, merge_commit_hash = self._run_merger_pass(
                                context=context,
                                runner=batch_runner,
                                reporter=reporter,
                                block_index=verification_block_index,
                                candidate=batch_merge_candidate,
                                execution_step=batch_merge_step,
                                memory_context=batch_memory_context,
                                failing_command="parallel-batch-merge",
                                failing_summary=merge_test_result.summary,
                                failing_stdout=read_text(merge_test_result.stdout_file),
                                failing_stderr=read_text(merge_test_result.stderr_file),
                                merge_targets=[step.step_id for step in batch_targets],
                                post_success_strategy="continue_cherry_pick",
                            )
                            if merge_run_result.returncode == 0 and merge_success and merge_commit_hash:
                                self._log_pass_result(
                                    context=context,
                                    reporter=reporter,
                                    block_index=verification_block_index,
                                    candidate=batch_merge_candidate,
                                    pass_name=merge_pass_name,
                                    run_result=merge_run_result,
                                    test_result=None,
                                    commit_hash=merge_commit_hash,
                                    rollback_status="not_needed",
                                    search_enabled=False,
                                )
                                merged_commit_hashes.append(merge_commit_hash)
                                merged_commit_by_step_id[result_step_id] = merge_commit_hash
                                continue
                        raise RuntimeError(
                            f"Parallel merge conflict while cherry-picking {worker_commit}: {', '.join(conflicted_files) or merge_result.stderr.strip() or 'unknown conflict'}"
                        )
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
                except Exception as exc:
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
                        if any(commit_hash.strip() for commit_hash in merged_commit_hashes):
                            close_block_index = max(1, context.loop_state.block_index + len(ordered_targets))
                            group_test_result = self._run_test_command(context, close_block_index, "parallel-batch-pass")
                            reporter.save_test_result(close_block_index, "parallel-batch-pass", group_test_result)
                        else:
                            group_test_result = self._run_test_command(context, verification_block_index, "parallel-batch-pass")
                            reporter.save_test_result(verification_block_index, "parallel-batch-pass", group_test_result)
                        if group_test_result and group_test_result.returncode != 0:
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
                pass_entry.update(
                    {
                        "repository_id": context.metadata.repo_id,
                        "repository_slug": context.metadata.slug,
                        "block_index": next_block_index,
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
        context = self.setup_local_project(project_dir=project_dir, runtime=runtime, branch=branch, origin_url=origin_url)
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
                    merge_result = self.git.try_cherry_pick(integration_context.paths.repo_dir, source_commit)
                    if merge_result.returncode == 0:
                        integration_head = self.git.current_revision(integration_context.paths.repo_dir)
                        integration_context.metadata.current_safe_revision = integration_head
                        integration_context.loop_state.current_safe_revision = integration_head
                        self.workspace.save_project(integration_context)
                        continue
                    if self._is_empty_cherry_pick_result(merge_result):
                        if self.git.cherry_pick_in_progress(integration_context.paths.repo_dir):
                            self.git.skip_cherry_pick(integration_context.paths.repo_dir)
                        integration_head = self.git.current_revision(integration_context.paths.repo_dir)
                        integration_context.metadata.current_safe_revision = integration_head
                        integration_context.loop_state.current_safe_revision = integration_head
                        self.workspace.save_project(integration_context)
                        continue
                    conflicted_files = self.git.conflicted_files(integration_context.paths.repo_dir)
                    merge_test_result = self._merge_conflict_test_result(
                        context=integration_context,
                        label="integration-merge",
                        command=f"git cherry-pick {source_commit}",
                        merge_result=merge_result,
                        conflicted_files=conflicted_files,
                    )
                    if conflicted_files and self.git.cherry_pick_in_progress(integration_context.paths.repo_dir):
                        merge_pass_name, merge_run_result, merge_success, merge_commit_hash = self._run_merger_pass(
                            context=integration_context,
                            runner=integration_runner,
                            reporter=integration_reporter,
                            block_index=merge_block_index,
                            candidate=merge_candidate,
                            execution_step=merge_step,
                            memory_context=integration_memory_context,
                            failing_command="integration-merge",
                            failing_summary=merge_test_result.summary,
                            failing_stdout=read_text(merge_test_result.stdout_file),
                            failing_stderr=read_text(merge_test_result.stderr_file),
                            merge_targets=merge_targets,
                        )
                        if merge_run_result.returncode == 0 and merge_success and merge_commit_hash:
                            self._log_pass_result(
                                context=integration_context,
                                reporter=integration_reporter,
                                block_index=merge_block_index,
                                candidate=merge_candidate,
                                pass_name=merge_pass_name,
                                run_result=merge_run_result,
                                test_result=None,
                                commit_hash=merge_commit_hash,
                                rollback_status="not_needed",
                                search_enabled=False,
                            )
                            integration_context.metadata.current_safe_revision = merge_commit_hash
                            integration_context.loop_state.current_safe_revision = merge_commit_hash
                            self.workspace.save_project(integration_context)
                            merge_block_index += 1
                            continue
                    raise RuntimeError(
                        f"{target_step.step_id} failed while merging {lineage.lineage_id}: "
                        f"{', '.join(conflicted_files) or merge_result.stderr.strip() or 'unknown conflict'}"
                    )

                integration_context.metadata.current_safe_revision = self.git.current_revision(integration_context.paths.repo_dir)
                integration_context.loop_state.current_safe_revision = integration_context.metadata.current_safe_revision
                self.workspace.save_project(integration_context)

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
                saved = self.save_execution_plan_state(context, plan_state)
                self.workspace.save_project(context)
                return context, saved, target_step
            except Exception as exc:
                if integration_context is not None:
                    self.git.abort_cherry_pick(integration_context.paths.repo_dir)
                    self.git.hard_reset(integration_context.paths.repo_dir, pre_join_safe_revision)
                if integration_info is not None:
                    self._cleanup_integration_worktree(context.paths.repo_dir, integration_info)
                self.git.hard_reset(context.paths.repo_dir, pre_join_safe_revision)
                context.metadata.current_safe_revision = pre_join_safe_revision
                context.loop_state.current_safe_revision = pre_join_safe_revision
                last_failure_note = str(exc).strip() or "Join execution failed."
                if attempt_index >= attempt_limit:
                    context.metadata.current_status = "failed"
                    target_step.status = "failed"
                    target_step.completed_at = None
                    target_step.commit_hash = None
                    target_step.notes = last_failure_note
                    saved = self.save_execution_plan_state(context, plan_state)
                    self.workspace.save_project(context)
                    return context, saved, target_step
                target_step.status = "running"
                target_step.completed_at = None
                target_step.commit_hash = None
                target_step.notes = (
                    f"Retrying join attempt {attempt_index + 1} of {attempt_limit} after failure: {last_failure_note}"
                )
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
        saved = self.save_execution_plan_state(context, plan_state)
        self.workspace.save_project(context)
        return context, saved, target_step

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

    def _execution_runtime_preflight_error(self, context: ProjectContext, runtime: RuntimeOptions) -> str:
        return provider_execution_preflight_error(
            str(getattr(runtime, "model_provider", "") or "").strip(),
            codex_path=str(getattr(runtime, "codex_path", "") or "").strip(),
            repo_dir=context.paths.repo_dir,
            provider_api_key_env=str(getattr(runtime, "provider_api_key_env", "") or "").strip(),
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
        if not is_quota_exhaustion_error(failure_detail):
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
            if safe_revision:
                self.git.hard_reset(context.paths.repo_dir, safe_revision)
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
            if not is_provider_fallbackable_error(candidate_detail):
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
            if not is_quota_exhaustion_error(error_detail):
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
        for directory in [worker_root, docs_dir, memory_dir, logs_dir, reports_dir, state_dir]:
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
            checkpoint_state_file=state_dir / "CHECKPOINTS.json",
            execution_plan_file=state_dir / "EXECUTION_PLAN.json",
            lineage_state_file=state_dir / "LINEAGES.json",
            ml_mode_state_file=state_dir / "ML_MODE_STATE.json",
            ml_step_report_file=state_dir / "ML_STEP_REPORT.json",
            ml_experiment_reports_dir=state_dir / "ml_experiments",
            ui_control_file=state_dir / "UI_RUN_CONTROL.json",
            ui_event_log_file=logs_dir / "ui_events.jsonl",
            execution_flow_svg_file=docs_dir / "EXECUTION_FLOW.svg",
            closeout_report_file=docs_dir / "CLOSEOUT_REPORT.md",
            closeout_report_docx_file=reports_dir / "CLOSEOUT_REPORT.docx",
            closeout_report_pptx_file=reports_dir / "CLOSEOUT_REPORT.pptx",
            ml_experiment_report_file=docs_dir / "ML_EXPERIMENT_REPORT.md",
            ml_experiment_results_svg_file=docs_dir / "ML_EXPERIMENT_RESULTS.svg",
        )

    def _copy_parallel_worker_support_files(self, context: ProjectContext, worker_paths: ProjectPaths) -> None:
        for source_dir, target_dir in [
            (context.paths.docs_dir, worker_paths.docs_dir),
            (context.paths.memory_dir, worker_paths.memory_dir),
            (context.paths.state_dir, worker_paths.state_dir),
        ]:
            ensure_dir(target_dir)
            if source_dir.exists():
                shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)

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
            context.metadata.current_status = self._status_from_plan_state(plan_state)
        else:
            step.status = failure_status
            step.completed_at = None
            step.commit_hash = None
            step.notes = worker_note or ("Parallel worker recovery pending." if failure_status == "pending" else "Parallel worker failed.")
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
                continue
            step.status = "failed"
            step.completed_at = None
            step.commit_hash = None
            step.notes = str(worker_result.get("notes") or "Parallel worker failed.").strip() or "Parallel worker failed."

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
            except Exception as exc:
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
            worker_result["status"] = "failed"
            worker_result["notes"] = preflight_error
            worker_result["test_summary"] = preflight_error
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
            worker_result.update(
                {
                    "status": "completed" if latest_block.get("status") == "completed" else "failed",
                    "notes": str(latest_block.get("test_summary") or "").strip() or "Parallel worker finished.",
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
                    "test_summary": str(latest_block.get("test_summary") or "").strip(),
                    "ml_report_payload": read_json(worker_context.paths.ml_step_report_file, default={}),
                }
            )
        except ImmediateStopRequested as exc:
            worker_result["status"] = "paused"
            worker_result["notes"] = str(exc).strip() or "Immediate stop requested."
        except Exception as exc:
            worker_result["status"] = "failed"
            worker_result["notes"] = str(exc).strip() or "Parallel worker failed."
        return worker_result

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

    def _next_logged_block_index(self, context: ProjectContext) -> int:
        latest_logged_block = read_last_jsonl(context.paths.block_log_file)
        latest_logged_block_index = int(latest_logged_block.get("block_index", 0)) if latest_logged_block else 0
        return max(1, context.loop_state.block_index + 1, latest_logged_block_index + 1)

    def _codex_failure_note(self, task_name: str, run_result: CodexRunResult) -> str:
        detail = self._run_result_failure_detail(run_result)
        summary = f"{task_name} Codex pass failed and changes were rolled back."
        if detail:
            return f"{summary} Cause: {detail}"
        return summary

    def _rolled_back_test_failure_note(self, test_result: TestRunResult, *, fallback_task_name: str) -> str:
        detail = str(test_result.summary or "").strip()
        if detail:
            return f"{detail} (changes were rolled back)"
        return f"{fallback_task_name} verification failed and changes were rolled back."

    def _execute_verified_repo_pass(
        self,
        *,
        context: ProjectContext,
        runner: CodexRunner,
        reporter: Reporter,
        prompt: str,
        pass_type: str,
        block_index: int,
        task_name: str,
        safe_revision: str,
    ) -> dict[str, object]:
        run_result = self._run_pass_with_provider_fallback(
            context=context,
            runner=runner,
            prompt=prompt,
            pass_type=pass_type,
            block_index=block_index,
            search_enabled=False,
            safe_revision=safe_revision,
            execution_step=None,
            provider_selection_source="auto",
        )
        run_result.changed_files = self.git.changed_files(context.paths.repo_dir)

        commit_hash: str | None = None
        rollback_status = "not_needed"
        test_result: TestRunResult | None = None
        changed_files = sorted(set(run_result.changed_files))
        success = False
        notes = ""

        if run_result.returncode != 0:
            self.git.hard_reset(context.paths.repo_dir, safe_revision)
            rollback_status = "rolled_back_to_safe_revision"
            notes = self._codex_failure_note(task_name, run_result)
        else:
            try:
                test_result = self._run_test_command(context, block_index, pass_type)
            except ImmediateStopRequested:
                self.git.hard_reset(context.paths.repo_dir, safe_revision)
                raise
            reporter.save_test_result(block_index, pass_type, test_result)
            if test_result.returncode != 0:
                self.git.hard_reset(context.paths.repo_dir, safe_revision)
                rollback_status = "rolled_back_to_safe_revision"
                notes = self._rolled_back_test_failure_note(test_result, fallback_task_name=task_name)
            else:
                if self.git.has_changes(context.paths.repo_dir):
                    commit_descriptor = build_commit_descriptor(context, pass_type, task_name)
                    commit_hash = self.git.commit_all(
                        context.paths.repo_dir,
                        commit_descriptor.message,
                        author_name=commit_descriptor.author_name,
                    )
                if commit_hash:
                    context.metadata.current_safe_revision = commit_hash
                    context.loop_state.current_safe_revision = commit_hash
                    pushed, push_reason = self._push_if_ready(
                        context,
                        context.paths.repo_dir,
                        context.metadata.branch,
                        commit_hash=commit_hash,
                    )
                    if not pushed and push_reason not in {"already_up_to_date"}:
                        notes = (notes + f" Push skipped: {push_reason}.").strip()
                success = True
                notes = test_result.summary

        return {
            "success": success,
            "notes": notes,
            "run_result": run_result,
            "test_result": test_result,
            "commit_hash": commit_hash,
            "changed_files": changed_files,
            "rollback_status": rollback_status,
            "safe_revision": commit_hash or safe_revision,
        }

    def _record_repo_pass(
        self,
        *,
        context: ProjectContext,
        reporter: Reporter,
        block_index: int,
        pass_type: str,
        selected_task: str,
        pass_result: dict[str, object],
        success_block_status: str,
        failure_block_status: str,
        extra_pass_fields: dict[str, object] | None = None,
        extra_block_fields: dict[str, object] | None = None,
    ) -> None:
        run_result = pass_result.get("run_result")
        test_result = pass_result.get("test_result")
        commit_hash = pass_result.get("commit_hash")
        rollback_status = str(pass_result.get("rollback_status") or "not_needed")
        changed_files = list(pass_result.get("changed_files") or [])
        success = bool(pass_result.get("success"))
        reporter.log_pass(
            {
                "repository_id": context.metadata.repo_id,
                "repository_slug": context.metadata.slug,
                "block_index": block_index,
                "pass_type": pass_type,
                "selected_task": selected_task,
                "changed_files": changed_files,
                "test_results": test_result.to_dict() if isinstance(test_result, TestRunResult) else None,
                "usage": run_result.usage if run_result else {},
                "duration_seconds": run_result.duration_seconds if run_result else 0.0,
                "codex_attempt_count": run_result.attempt_count if run_result else 0,
                "codex_diagnostics": run_result.diagnostics if run_result else {},
                "codex_return_code": run_result.returncode if run_result else None,
                "commit_hash": commit_hash,
                "rollback_status": rollback_status,
                "search_enabled": False,
                **(extra_pass_fields or {}),
            }
        )
        reporter.log_block(
            {
                "repository_id": context.metadata.repo_id,
                "repository_slug": context.metadata.slug,
                "block_index": block_index,
                "status": success_block_status if success else failure_block_status,
                "selected_task": selected_task,
                "changed_files": changed_files,
                "test_summary": str(pass_result.get("notes") or "").strip(),
                "commit_hashes": [str(commit_hash)] if commit_hash else [],
                "rollback_status": rollback_status,
                **(extra_block_fields or {}),
            }
        )
        reporter.write_block_review(
            reflection_markdown(
                selected_task,
                str(pass_result.get("notes") or "").strip() or "No summary recorded.",
                changed_files,
                [str(commit_hash)] if commit_hash else [],
            )
        )
        reporter.append_attempt_history(
            attempt_history_entry(
                block_index,
                selected_task,
                success_block_status.replace("_", " ") if success else failure_block_status.replace("_", " "),
                [str(commit_hash)] if commit_hash else [],
            )
        )

    def _run_optional_closeout_optimization(
        self,
        *,
        context: ProjectContext,
        plan_state: ExecutionPlanState,
        runner: CodexRunner,
        reporter: Reporter,
        safe_revision: str,
        block_index: int,
    ) -> tuple[str, int]:
        scan_result = scan_optimization_candidates(context.paths.repo_dir, context.runtime)
        if not scan_result.candidates:
            return safe_revision, block_index

        optimization_task = f"Pre-closeout optimization ({scan_result.mode})"
        context.loop_state.current_task = optimization_task
        self.workspace.save_project(context)
        pass_result: dict[str, object] = {
            "success": False,
            "notes": "",
            "run_result": None,
            "test_result": None,
            "commit_hash": None,
            "changed_files": [],
            "rollback_status": "not_needed",
            "safe_revision": safe_revision,
        }
        try:
            pass_result = self._execute_verified_repo_pass(
                context=context,
                runner=runner,
                reporter=reporter,
                prompt=optimization_prompt(context, plan_state, scan_result),
                pass_type="project-optimization-pass",
                block_index=block_index,
                task_name=optimization_task,
                safe_revision=safe_revision,
            )
        except Exception as exc:
            self.git.hard_reset(context.paths.repo_dir, safe_revision)
            pass_result = {
                "success": False,
                "notes": str(exc).strip() or "Pre-closeout optimization failed.",
                "run_result": pass_result.get("run_result"),
                "test_result": None,
                "commit_hash": None,
                "changed_files": self.git.changed_files(context.paths.repo_dir),
                "rollback_status": "rolled_back_to_safe_revision",
                "safe_revision": safe_revision,
            }

        self._record_repo_pass(
            context=context,
            reporter=reporter,
            block_index=block_index,
            pass_type="project-optimization-pass",
            selected_task=optimization_task,
            pass_result=pass_result,
            success_block_status="optimization_completed",
            failure_block_status="optimization_failed",
            extra_pass_fields={
                "optimization_mode": scan_result.mode,
                "optimization_candidates": [item.to_dict() for item in scan_result.candidates],
                "scanned_file_count": scan_result.scanned_file_count,
            },
            extra_block_fields={
                "optimization_mode": scan_result.mode,
                "candidate_files": list(scan_result.candidate_files),
            },
        )
        return str(pass_result.get("safe_revision") or safe_revision), block_index + 1

    def _parse_iso_timestamp(self, value: str | None) -> datetime | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    def _closeout_run_is_stale(self, context: ProjectContext, plan_state: ExecutionPlanState) -> bool:
        if plan_state.closeout_status != "running":
            return False
        if context.metadata.current_status != "running:closeout":
            return True
        heartbeat = max(
            (
                item
                for item in (
                    self._parse_iso_timestamp(context.metadata.last_run_at),
                    self._parse_iso_timestamp(plan_state.closeout_started_at),
                )
                if item is not None
            ),
            default=None,
        )
        if heartbeat is None:
            return True
        return datetime.now(tz=UTC) - heartbeat > self._STALE_CLOSEOUT_TIMEOUT

    def run_execution_closeout(
        self,
        project_dir: Path,
        runtime: RuntimeOptions,
        branch: str = "main",
        origin_url: str = "",
    ) -> tuple[ProjectContext, ExecutionPlanState]:
        context = self.setup_local_project(project_dir=project_dir, runtime=runtime, branch=branch, origin_url=origin_url)
        plan_state = self.load_execution_plan_state(context)
        if not plan_state.steps:
            raise RuntimeError("No saved execution plan exists for this project.")
        if not self._all_steps_completed(plan_state.steps):
            raise RuntimeError("Closeout can run only after all execution tasks are completed.")
        if plan_state.closeout_status == "running":
            if not self._closeout_run_is_stale(context, plan_state):
                raise RuntimeError("Closeout is already running.")
            plan_state.closeout_status = "failed"
            plan_state.closeout_notes = "Recovered a stale closeout state before retrying."
            context.metadata.current_status = self._status_from_plan_state(plan_state)
            self.save_execution_plan_state(context, plan_state)
            self.workspace.save_project(context)

        previous_runtime = context.runtime
        context.runtime = RuntimeOptions(
            **{
                **previous_runtime.to_dict(),
                "test_cmd": plan_state.default_test_command or runtime.test_cmd,
                "allow_push": True,
                "approval_mode": runtime.approval_mode,
                "sandbox_mode": runtime.sandbox_mode,
                "require_checkpoint_approval": False,
                "checkpoint_interval_blocks": 1,
            }
        )
        closeout_started_at = now_utc_iso()
        plan_state.closeout_status = "running"
        plan_state.closeout_started_at = closeout_started_at
        plan_state.closeout_completed_at = None
        plan_state.closeout_commit_hash = None
        plan_state.closeout_notes = ""
        context.metadata.current_status = "running:closeout"
        context.metadata.last_run_at = closeout_started_at
        context.loop_state.current_task = "Project closeout"
        self.save_execution_plan_state(context, plan_state)
        self.workspace.save_project(context)

        runner = CodexRunner(context.runtime.codex_path)
        reporter = Reporter(context)
        repo_inputs = scan_repository_inputs(context.paths.repo_dir)
        safe_revision = context.metadata.current_safe_revision or self.git.current_revision(context.paths.repo_dir)
        next_block_index = self._next_logged_block_index(context)
        safe_revision, next_block_index = self._run_optional_closeout_optimization(
            context=context,
            plan_state=plan_state,
            runner=runner,
            reporter=reporter,
            safe_revision=safe_revision,
            block_index=next_block_index,
        )
        prompt = finalization_prompt(
            context=context,
            plan_state=plan_state,
            repo_inputs=repo_inputs,
        )
        closeout_block_index = next_block_index
        closeout_task = "Project closeout"
        context.loop_state.current_task = closeout_task
        self.workspace.save_project(context)
        closeout_result: dict[str, object] = {
            "success": False,
            "notes": "",
            "run_result": None,
            "test_result": None,
            "commit_hash": None,
            "changed_files": [],
            "rollback_status": "not_needed",
            "safe_revision": safe_revision,
        }
        closeout_interrupted = False

        try:
            closeout_result = self._execute_verified_repo_pass(
                context=context,
                runner=runner,
                reporter=reporter,
                prompt=prompt,
                pass_type="project-closeout-pass",
                block_index=closeout_block_index,
                task_name=closeout_task,
                safe_revision=safe_revision,
            )
            if bool(closeout_result.get("success")):
                plan_state.closeout_status = "completed"
                plan_state.closeout_completed_at = now_utc_iso()
                plan_state.closeout_commit_hash = str(closeout_result.get("commit_hash") or "") or None
                plan_state.closeout_notes = str(closeout_result.get("notes") or "").strip()
            else:
                plan_state.closeout_status = "failed"
                plan_state.closeout_notes = str(closeout_result.get("notes") or "").strip()
        except ImmediateStopRequested as exc:
            self.git.hard_reset(context.paths.repo_dir, safe_revision)
            closeout_interrupted = True
            plan_state.closeout_status = "not_started"
            plan_state.closeout_started_at = None
            plan_state.closeout_completed_at = None
            plan_state.closeout_commit_hash = None
            plan_state.closeout_notes = str(exc).strip() or "Immediate stop requested."
        except Exception as exc:
            plan_state.closeout_status = "failed"
            plan_state.closeout_notes = str(exc).strip() or "Closeout failed."
            raise
        finally:
            closeout_result["notes"] = plan_state.closeout_notes
            if not closeout_interrupted:
                self._record_repo_pass(
                    context=context,
                    reporter=reporter,
                    block_index=closeout_block_index,
                    pass_type="project-closeout-pass",
                    selected_task=closeout_task,
                    pass_result=closeout_result,
                    success_block_status="closeout_completed",
                    failure_block_status="closeout_failed",
                )
            context.runtime = previous_runtime
            if normalize_workflow_mode(context.runtime.workflow_mode) == "ml":
                self.refresh_ml_mode_outputs(context)
            context.metadata.current_status = self._status_from_plan_state(plan_state)
            context.metadata.last_run_at = now_utc_iso()
            self.save_execution_plan_state(context, plan_state)
            self.workspace.save_project(context)
            reporter.write_status_report()
            if context.runtime.generate_word_report:
                reporter.write_closeout_word_report()
            if plan_state.closeout_status != "completed" and not closeout_interrupted:
                self._report_failure(
                    context,
                    reporter,
                    failure_type="closeout_failed",
                    summary=plan_state.closeout_notes or "Closeout failed.",
                    block_index=closeout_block_index,
                    selected_task=closeout_task,
                )
            elif plan_state.closeout_status == "completed":
                self._maybe_open_pull_request(
                    context,
                    head_branch=context.metadata.branch,
                    title=plan_state.plan_title.strip() or "jakal-flow closeout",
                    body=(
                        "Automatically opened by jakal-flow after a successful closeout push.\n\n"
                        f"- Branch: `{context.metadata.branch}`\n"
                        f"- Closeout commit: `{plan_state.closeout_commit_hash or 'unknown'}`\n"
                    ),
                )

        return context, plan_state

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
            repo_inputs = scan_repository_inputs(context.paths.repo_dir)
            is_mature, maturity_details = assess_repository_maturity(context.paths.repo_dir, repo_inputs)
            plan_text = self._resolve_plan_text(
                context=context,
                runtime=runtime,
                repo_inputs=repo_inputs,
                is_mature=is_mature,
                maturity_details=maturity_details,
                plan_path=plan_path,
                plan_input=plan_input,
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
        except Exception as exc:
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
                repo_inputs = scan_repository_inputs(context.paths.repo_dir)
                is_mature, maturity_details = assess_repository_maturity(context.paths.repo_dir, repo_inputs)
                updated_plan_text = self._read_supplied_plan_text(plan_path, plan_input)
                if updated_plan_text:
                    resolved_plan_text = self._resolve_plan_text(
                        context=context,
                        runtime=runtime,
                        repo_inputs=repo_inputs,
                        is_mature=is_mature,
                        maturity_details=maturity_details,
                        plan_path=plan_path,
                        plan_input=plan_input,
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
            if context.loop_state.stop_requested:
                context.loop_state.stop_reason = "user stop requested"
                context.metadata.current_status = "ready"
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

    def plan_work(
        self,
        repo_url: str,
        branch: str,
        runtime: RuntimeOptions,
        plan_path: Path | None = None,
        plan_input: str = "",
    ) -> dict[str, object]:
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
            repo_inputs = scan_repository_inputs(context.paths.repo_dir)
            is_mature, maturity_details = assess_repository_maturity(context.paths.repo_dir, repo_inputs)
            plan_text = self._resolve_plan_text(
                context=context,
                runtime=runtime,
                repo_inputs=repo_inputs,
                is_mature=is_mature,
                maturity_details=maturity_details,
                plan_path=plan_path,
                plan_input=plan_input,
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
        if data is None:
            checkpoints = build_checkpoint_timeline(read_text(context.paths.plan_file), context.runtime.checkpoint_interval_blocks)
            data = {"checkpoints": [checkpoint.to_dict() for checkpoint in checkpoints]}
            write_json(context.paths.checkpoint_state_file, data)
            write_text(context.paths.checkpoint_timeline_file, checkpoint_timeline_markdown(checkpoints))
        return data

    def approve_checkpoint(self, repo_url: str, branch: str, review_notes: str = "", push: bool = True) -> dict:
        context = self.status(repo_url, branch)
        data = self.checkpoints(repo_url, branch)
        checkpoints = data.get("checkpoints", [])
        target: dict | None = None
        for checkpoint in checkpoints:
            if checkpoint.get("status") == "awaiting_review":
                target = checkpoint
                break
        if target is None and context.loop_state.current_checkpoint_id:
            for checkpoint in checkpoints:
                if checkpoint.get("checkpoint_id") == context.loop_state.current_checkpoint_id:
                    target = checkpoint
                    break
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
        ensure_dir(context.paths.ml_experiment_reports_dir)
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
        if not context.paths.execution_flow_svg_file.exists():
            write_text(
                context.paths.execution_flow_svg_file,
                execution_plan_svg(f"{context.metadata.display_name or context.metadata.slug} execution flow", []),
            )
        if not context.paths.ml_experiment_results_svg_file.exists():
            write_text(context.paths.ml_experiment_results_svg_file, self._ml_results_svg([]))

    def _execution_step_rationale(self, step: ExecutionStep, test_command: str) -> str:
        details = step.codex_description or step.display_description or "Complete the saved execution checkpoint with a small, safe change."
        success = step.success_criteria or "The verification command exits successfully."
        ui_hint = step.display_description.strip()
        dependency_hint = f" Dependencies: {', '.join(step.depends_on)}." if step.depends_on else ""
        ownership_hint = f" Owned paths: {', '.join(step.owned_paths)}." if step.owned_paths else ""
        step_kind = self._step_kind(step)
        kind_hint = ""
        if step_kind != "task":
            kind_hint = f" Step kind: {step_kind}."
        metadata_hint = ""
        if step.metadata:
            metadata_hint = f" Metadata: {json.dumps(step.metadata, ensure_ascii=False, sort_keys=True)}."
        if ui_hint and ui_hint != details:
            return f"UI description: {ui_hint}. Execution instruction: {details}.{kind_hint}{dependency_hint}{ownership_hint}{metadata_hint} Verification command: {test_command}. Success criteria: {success}"
        return f"{details}.{kind_hint}{dependency_hint}{ownership_hint}{metadata_hint} Verification command: {test_command}. Success criteria: {success}"

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
            regression_failure = search_pass.returncode == 0
            failure_summary = (
                "Search-enabled Codex pass regressed tests and was rolled back."
                if regression_failure
                else self._codex_failure_note(selected_task, search_pass)
            )
            if regression_failure:
                context.loop_state.counters.regression_failures += 1
                context.loop_state.stop_reason = self._stop_reason(context)
            else:
                context.loop_state.stop_reason = failure_summary
            memory.record_failure(
                task=selected_task,
                summary=failure_summary,
                tags=["search", "regression"] if regression_failure else ["search", "codex_failure"],
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
                    "status": "rolled_back",
                    "selected_task": selected_task,
                    "changed_files": [],
                    "test_summary": failure_summary,
                    "commit_hashes": [],
                    "rollback_status": "rolled_back_to_safe_revision",
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
            self._mark_checkpoint_if_due(context, block_index, block_commit_hashes)
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
        run_result.changed_files = self.git.changed_files(context.paths.repo_dir)
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
            test_result = self._run_test_command(context, block_index, pass_name)
        except ImmediateStopRequested:
            self.git.hard_reset(context.paths.repo_dir, safe_revision)
            raise
        reporter.save_test_result(block_index, pass_name, test_result)
        commit_hash: str | None = None
        rollback_status = "not_needed"
        if test_result.returncode != 0:
            self._log_pass_result(
                context=context,
                reporter=reporter,
                block_index=block_index,
                candidate=candidate,
                pass_name=pass_name,
                run_result=run_result,
                test_result=test_result,
                commit_hash=None,
                rollback_status="debugger_invoked",
                search_enabled=search_enabled,
            )
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

    def _run_test_command(self, context: ProjectContext, block_index: int, label: str) -> TestRunResult:
        return self.verification.run(
            context=context,
            block_index=block_index,
            label=label,
            command=context.runtime.test_cmd,
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

    def _mark_checkpoint_if_due(self, context: ProjectContext, block_index: int, commit_hashes: list[str]) -> None:
        if not context.runtime.require_checkpoint_approval:
            return
        data = read_json(context.paths.checkpoint_state_file, default={"checkpoints": []})
        checkpoints = data.get("checkpoints", [])
        changed = False
        for checkpoint in checkpoints:
            if checkpoint.get("status") != "pending":
                continue
            if int(checkpoint.get("target_block", 0)) <= block_index:
                checkpoint["status"] = "awaiting_review"
                checkpoint["reached_at"] = now_utc_iso()
                checkpoint["commit_hashes"] = commit_hashes
                context.loop_state.current_checkpoint_id = checkpoint.get("checkpoint_id")
                context.loop_state.pending_checkpoint_approval = True
                changed = True
                break
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

    def _maybe_open_pull_request(
        self,
        context: ProjectContext,
        *,
        head_branch: str,
        base_branch: str = "",
        title: str,
        body: str = "",
        draft: bool = False,
        status_filename: str = "latest_pull_request_status.json",
    ) -> dict:
        reporter = Reporter(context)
        result = reporter.ensure_pull_request(
            head_branch=head_branch,
            base_branch=base_branch,
            title=title,
            body=body,
            draft=draft,
        )
        write_json(
            context.paths.reports_dir / status_filename,
            {
                "generated_at": now_utc_iso(),
                "head_branch": head_branch,
                "base_branch": base_branch,
                "title": title,
                "result": result,
            },
        )
        return result

    def _read_supplied_plan_text(self, plan_path: Path | None, plan_input: str) -> str:
        if plan_input.strip():
            return plan_input.strip()
        if plan_path:
            return Path(plan_path).read_text(encoding="utf-8").strip()
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
        prompt = bootstrap_plan_prompt(context, repo_inputs, user_prompt)
        result = self._run_pass_with_provider_fallback(
            context=context,
            runner=runner,
            prompt=prompt,
            pass_type="init-project-plan",
            block_index=0,
            search_enabled=False,
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
    ) -> tuple[list, str]:
        if work_items:
            remaining_items = work_items[max(0, context.loop_state.block_index - 1):]
            mid_term_text, mid_items = build_mid_term_plan_from_user_items(remaining_items or work_items)
            return mid_items, mid_term_text

        planned_items = self._generate_codex_work_items(
            context=context,
            runner=runner,
            plan_text=plan_text,
            max_items=max_items,
        )
        if planned_items:
            mid_term_text, mid_items = build_mid_term_plan_from_plan_items(
                planned_items,
                "This plan was generated by Codex from the current repository state and saved project plan.",
            )
            valid_subset, violations = validate_mid_term_subset(mid_term_text, plan_text)
            if valid_subset:
                return mid_items, mid_term_text
            write_text(context.paths.reports_dir / "plan_scope_violation.txt", "\n".join(violations) + "\n")

        mid_term_text, mid_items = build_mid_term_plan(plan_text)
        valid_subset, violations = validate_mid_term_subset(mid_term_text, plan_text)
        if not valid_subset:
            raise RuntimeError(f"Mid-term plan violated saved plan scope: {violations}")
        return mid_items, mid_term_text

    def _generate_codex_work_items(
        self,
        context: ProjectContext,
        runner: CodexRunner,
        plan_text: str,
        max_items: int,
    ) -> list:
        repo_inputs = scan_repository_inputs(context.paths.repo_dir)
        memory_context = MemoryStore(context.paths).render_context(plan_text)
        prompt = work_breakdown_prompt(
            context=context,
            repo_inputs=repo_inputs,
            plan_text=plan_text,
            memory_context=memory_context,
            max_items=max_items,
        )
        result = self._run_pass_with_provider_fallback(
            context=context,
            runner=runner,
            prompt=prompt,
            pass_type="plan-work-breakdown",
            block_index=max(0, context.loop_state.block_index),
            search_enabled=False,
        )
        if result.returncode != 0:
            return []
        return parse_work_breakdown_response(result.last_message or "", limit=max_items)
