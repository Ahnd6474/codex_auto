from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from html import escape
import shutil
from pathlib import Path
from uuid import uuid4

from .environment import ensure_gitignore, ensure_virtualenv
from .codex_runner import CodexRunner
from .git_ops import GitOps
from .memory import MemoryStore
from .model_selection import normalize_reasoning_effort
from .models import CandidateTask, Checkpoint, ExecutionPlanState, ExecutionStep, LoopState, MLExperimentRecord, MLModeState, ProjectContext, ProjectPaths, RepoMetadata, RuntimeOptions, TestRunResult
from .planning import (
    FINALIZATION_PROMPT_FILENAME,
    attempt_history_entry,
    assess_repository_maturity,
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
    load_plan_generation_prompt_template,
    parse_execution_plan_response,
    parse_work_breakdown_response,
    prompt_to_execution_plan_prompt,
    reflection_markdown,
    scan_repository_inputs,
    select_candidate,
    load_step_execution_prompt_template,
    validate_mid_term_subset,
    work_breakdown_prompt,
    write_active_task,
    load_source_prompt_template,
)
from .reporting import Reporter
from .utils import compact_text, ensure_dir, normalize_workflow_mode, now_utc_iso, read_json, read_last_jsonl, read_text, write_json, write_text
from .verification import VerificationRunner
from .workspace import WorkspaceManager


class Orchestrator:
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
            safe_revision = self.git.create_initial_commit(
                context.paths.repo_dir,
                "chore: initialize jakal-flow workspace",
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
    ) -> tuple[ProjectContext, ExecutionPlanState]:
        context = self.setup_local_project(project_dir=project_dir, runtime=runtime, branch=branch, origin_url=origin_url)
        project_prompt = project_prompt.strip()
        previous_plan_state = self.load_execution_plan_state(context)
        workflow_mode = normalize_workflow_mode(runtime.workflow_mode)
        planning_prompt_template = load_plan_generation_prompt_template(self._normalize_execution_mode(runtime.execution_mode), workflow_mode)
        repo_inputs = scan_repository_inputs(context.paths.repo_dir)
        runner = CodexRunner(context.runtime.codex_path)
        prompt = prompt_to_execution_plan_prompt(
            context=context,
            repo_inputs=repo_inputs,
            user_prompt=project_prompt,
            max_steps=max_steps,
            execution_mode=self._normalize_execution_mode(runtime.execution_mode),
            template_text=planning_prompt_template,
        )
        result = runner.run_pass(
            context=context,
            prompt=prompt,
            pass_type="plan-interactive-execution",
            block_index=max(0, context.loop_state.block_index),
            search_enabled=False,
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

        plan_state = ExecutionPlanState(
            plan_title=plan_title.strip() or context.metadata.display_name or context.metadata.slug,
            project_prompt=project_prompt.strip(),
            summary=summary.strip(),
            workflow_mode=workflow_mode,
            execution_mode=self._normalize_execution_mode(runtime.execution_mode),
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
        if not state.default_test_command:
            state.default_test_command = context.runtime.test_cmd
        fallback_effort = normalize_reasoning_effort(context.runtime.effort, fallback="high")
        for step in state.steps:
            step.reasoning_effort = normalize_reasoning_effort(step.reasoning_effort, fallback=fallback_effort)
        return state

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
        remaining = [step for step in plan_state.steps if step.status != "completed"]
        if not remaining:
            return []
        if self._normalize_execution_mode(plan_state.execution_mode) != "parallel":
            return [[step] for step in remaining]
        if self._plan_uses_dag_parallelism(plan_state.steps):
            completed_ids = {step.step_id for step in plan_state.steps if step.status == "completed"}
            ready = [
                step
                for step in plan_state.steps
                if step.status != "completed"
                and all(dep in completed_ids for dep in step.depends_on)
            ]
            if not ready:
                raise RuntimeError("No dependency-ready execution step is available. Check the DAG dependencies for cycles or blocked nodes.")
            return self._dag_ready_batches(ready)

        batches: list[list[ExecutionStep]] = []
        index = 0
        while index < len(remaining):
            current = remaining[index]
            group = current.parallel_group.strip()
            if not group:
                batches.append([current])
                index += 1
                continue
            batch = [current]
            index += 1
            while index < len(remaining) and remaining[index].parallel_group.strip() == group:
                batch.append(remaining[index])
                index += 1
            batches.append(batch)
        return batches

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
            normalized_steps.append(
                ExecutionStep(
                    step_id=id_map[raw_id],
                    title=step.title.strip(),
                    display_description=step.display_description.strip(),
                    codex_description=step.codex_description.strip() or step.display_description.strip() or step.title.strip(),
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
                    metadata=deepcopy(step.metadata) if isinstance(step.metadata, dict) else {},
                )
            )
        if execution_mode == "parallel" and self._plan_uses_dag_parallelism(normalized_steps):
            self._validate_parallel_execution_steps(normalized_steps)
        return normalized_steps

    def _normalize_owned_path(self, value: str) -> str:
        normalized = str(value).strip().replace("\\", "/")
        while normalized.startswith("./"):
            normalized = normalized[2:]
        return normalized.rstrip("/")

    def _plan_uses_dag_parallelism(self, steps: list[ExecutionStep]) -> bool:
        return any(step.depends_on or step.owned_paths for step in steps)

    def _validate_parallel_execution_steps(self, steps: list[ExecutionStep]) -> None:
        step_ids = {step.step_id for step in steps}
        indegree = {step.step_id: 0 for step in steps}
        edges: dict[str, list[str]] = {step.step_id: [] for step in steps}
        for step in steps:
            for dependency in step.depends_on:
                if dependency not in step_ids:
                    raise ValueError(f"Unknown dependency reference: {dependency}")
                if dependency == step.step_id:
                    raise ValueError(f"{step.step_id} cannot depend on itself.")
                indegree[step.step_id] += 1
                edges[dependency].append(step.step_id)
        ready = [step.step_id for step in steps if indegree[step.step_id] == 0]
        visited = 0
        while ready:
            current = ready.pop(0)
            visited += 1
            for neighbor in edges[current]:
                indegree[neighbor] -= 1
                if indegree[neighbor] == 0:
                    ready.append(neighbor)
        if visited != len(steps):
            raise ValueError("Parallel execution plan contains a dependency cycle.")

    def _dag_ready_batches(self, ready_steps: list[ExecutionStep]) -> list[list[ExecutionStep]]:
        batches: list[list[ExecutionStep]] = []
        current_batch: list[ExecutionStep] = []
        current_paths: list[str] = []
        for step in ready_steps:
            if not step.owned_paths:
                if current_batch:
                    batches.append(current_batch)
                    current_batch = []
                    current_paths = []
                batches.append([step])
                continue
            conflict = any(
                self._owned_paths_conflict(candidate_path, existing_path)
                for candidate_path in step.owned_paths
                for existing_path in current_paths
            )
            if conflict and current_batch:
                batches.append(current_batch)
                current_batch = [step]
                current_paths = list(step.owned_paths)
                continue
            current_batch.append(step)
            current_paths.extend(step.owned_paths)
        if current_batch:
            batches.append(current_batch)
        return batches or [[step] for step in ready_steps]

    def _owned_paths_conflict(self, left: str, right: str) -> bool:
        normalized_left = self._normalize_owned_path(left).lower()
        normalized_right = self._normalize_owned_path(right).lower()
        if not normalized_left or not normalized_right:
            return False
        return (
            normalized_left == normalized_right
            or normalized_left.startswith(f"{normalized_right}/")
            or normalized_right.startswith(f"{normalized_left}/")
        )

    def run_saved_execution_step(
        self,
        project_dir: Path,
        runtime: RuntimeOptions,
        step_id: str | None = None,
        branch: str = "main",
        origin_url: str = "",
    ) -> tuple[ProjectContext, ExecutionPlanState, ExecutionStep]:
        context = self.setup_local_project(project_dir=project_dir, runtime=runtime, branch=branch, origin_url=origin_url)
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

        for step in plan_state.steps:
            if step.step_id == target_step.step_id:
                step.status = "running"
                step.started_at = step.started_at or now_utc_iso()
                step.notes = ""
            elif step.status == "running":
                step.status = "paused"
        plan_state.default_test_command = runtime.test_cmd
        plan_state = self.save_execution_plan_state(context, plan_state)

        previous_runtime = context.runtime
        context.runtime = RuntimeOptions(
            **{
                **previous_runtime.to_dict(),
                "test_cmd": target_step.test_command or runtime.test_cmd,
                "effort": normalize_reasoning_effort(
                    target_step.reasoning_effort,
                    fallback=normalize_reasoning_effort(runtime.effort, fallback="high"),
                ),
                "max_blocks": 1,
                "allow_push": True,
                "approval_mode": runtime.approval_mode,
                "sandbox_mode": runtime.sandbox_mode,
                "require_checkpoint_approval": False,
                "checkpoint_interval_blocks": 1,
            }
        )
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
        if len(step_ids) < 2:
            raise ValueError("Parallel execution batch requires at least two step ids.")

        ordered_targets: list[ExecutionStep] = []
        requested = {step_id.strip() for step_id in step_ids if step_id.strip()}
        for step in plan_state.steps:
            if step.step_id in requested:
                if step.status == "completed":
                    raise RuntimeError(f"{step.step_id} is already completed.")
                ordered_targets.append(step)
        if len(ordered_targets) < 2:
            raise RuntimeError("No remaining parallel batch steps were found.")
        allowed_batches = [
            [item.step_id for item in batch]
            for batch in self.pending_execution_batches(plan_state)
            if len(batch) > 1
        ]
        requested_signature = [step.step_id for step in ordered_targets]
        if requested_signature not in allowed_batches:
            raise RuntimeError("Requested parallel batch is not currently ready in the execution DAG.")

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
                "parallel_workers": self._parallel_worker_count(runtime.parallel_workers),
                "allow_push": True,
                "approval_mode": runtime.approval_mode,
                "sandbox_mode": runtime.sandbox_mode,
                "require_checkpoint_approval": False,
                "checkpoint_interval_blocks": 1,
            }
        )
        context.metadata.current_status = "running:parallel"
        context.metadata.last_run_at = batch_started_at
        context.loop_state.current_task = f"Parallel batch {batch_label}"
        self.save_execution_plan_state(context, plan_state)
        self.workspace.save_project(context)

        reporter = Reporter(context)
        base_revision = context.metadata.current_safe_revision or self.git.current_revision(context.paths.repo_dir)
        batch_token = f"{now_utc_iso().replace(':', '').replace('-', '').replace('+', '').replace('T', 't')}-{uuid4().hex[:8]}"
        worker_results: list[dict[str, object]] = []
        merged_commit_hashes: list[str] = []
        group_test_result: TestRunResult | None = None
        rollback_status = "not_needed"
        final_status = "completed"
        batch_summary = ""
        failure_extra: dict[str, object] | None = None

        try:
            worker_limit = min(len(ordered_targets), self._parallel_worker_count(context.runtime.parallel_workers))
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
                    by_step_id[str(result["step_id"])] = result
                worker_results = [by_step_id[step.step_id] for step in ordered_targets]

            failed_worker = next((item for item in worker_results if str(item.get("status")) != "completed"), None)
            if failed_worker is not None:
                final_status = "failed"
                rollback_status = "not_needed"
                batch_summary = str(failed_worker.get("notes") or "Parallel worker failed.").strip()
                for step in ordered_targets:
                    step.status = "failed"
                    step.notes = batch_summary if step.step_id == failed_worker.get("step_id") else "Parallel batch aborted because another worker failed."
                context.metadata.current_status = "failed"
            else:
                try:
                    for result in worker_results:
                        worker_commit = str(result.get("commit_hash") or "").strip()
                        if not worker_commit:
                            merged_commit_hashes.append("")
                            continue
                        merge_result = self.git.try_cherry_pick(context.paths.repo_dir, worker_commit)
                        if merge_result.returncode == 0:
                            merged_commit_hashes.append(self.git.current_revision(context.paths.repo_dir))
                            continue
                        conflicted_files = self.git.conflicted_files(context.paths.repo_dir)
                        failure_extra = {"conflict": self._parallel_conflict_details(conflicted_files)}
                        raise RuntimeError(
                            f"Parallel merge conflict while cherry-picking {worker_commit}: {', '.join(conflicted_files) or merge_result.stderr.strip() or 'unknown conflict'}"
                        )
                except Exception as exc:
                    self.git.abort_cherry_pick(context.paths.repo_dir)
                    self.git.hard_reset(context.paths.repo_dir, base_revision)
                    rollback_status = "rolled_back_to_safe_revision"
                    final_status = "failed"
                    batch_summary = str(exc).strip() or "Parallel merge failed."
                    for step in ordered_targets:
                        step.status = "failed"
                        step.notes = batch_summary
                    context.metadata.current_status = "failed"
                else:
                    verification_block_index = max(1, context.loop_state.block_index + len(ordered_targets))
                    if any(commit_hash.strip() for commit_hash in merged_commit_hashes):
                        close_block_index = max(1, context.loop_state.block_index + len(ordered_targets))
                        group_test_result = self._run_test_command(context, close_block_index, "parallel-batch-pass")
                        reporter.save_test_result(close_block_index, "parallel-batch-pass", group_test_result)
                    else:
                        group_test_result = self._run_test_command(context, verification_block_index, "parallel-batch-pass")
                        reporter.save_test_result(verification_block_index, "parallel-batch-pass", group_test_result)
                    if group_test_result and group_test_result.returncode != 0:
                        batch_debug_step = self._build_parallel_batch_debug_step(
                            ordered_targets,
                            plan_state.default_test_command or runtime.test_cmd,
                        )
                        batch_candidate = CandidateTask(
                            candidate_id="parallel-batch-debug",
                            title=batch_debug_step.title,
                            rationale=self._execution_step_rationale(batch_debug_step, batch_debug_step.test_command),
                            plan_refs=[step.step_id for step in ordered_targets],
                            score=1.0,
                        )
                        batch_memory_context = MemoryStore(context.paths).render_context(read_text(context.paths.mid_term_plan_file))
                        batch_runner = CodexRunner(context.runtime.codex_path)
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
                            rollback_status = "rolled_back_to_safe_revision"
                            final_status = "failed"
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
                            for step in ordered_targets:
                                step.status = "failed"
                                step.notes = batch_summary
                            context.metadata.current_status = "failed"
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
                            merged_commits = [item for item in merged_commit_hashes if item]
                            if merged_commits:
                                last_commit = merged_commits[-1]
                                context.metadata.current_safe_revision = last_commit
                                context.loop_state.current_safe_revision = last_commit
                                context.loop_state.last_commit_hash = last_commit
                            for index, step in enumerate(ordered_targets):
                                step.status = "completed"
                                step.completed_at = now_utc_iso()
                                merged_commit = merged_commit_hashes[index] if index < len(merged_commit_hashes) else ""
                                step.commit_hash = merged_commit or None
                                worker_note = str(worker_results[index].get("test_summary") or "").strip()
                                step.notes = worker_note if worker_note else debug_test_result.summary
                            context.metadata.current_status = self._status_from_plan_state(plan_state)
                    else:
                        batch_summary = group_test_result.summary if group_test_result else "Parallel batch completed successfully."
                        for index, step in enumerate(ordered_targets):
                            step.status = "completed"
                            step.completed_at = now_utc_iso()
                            merged_commit = merged_commit_hashes[index] if index < len(merged_commit_hashes) else ""
                            step.commit_hash = merged_commit or None
                            worker_note = str(worker_results[index].get("test_summary") or "").strip()
                            step.notes = worker_note if worker_note else batch_summary
                        merged_commits = [item for item in merged_commit_hashes if item]
                        if merged_commits:
                            last_commit = merged_commits[-1]
                            context.metadata.current_safe_revision = last_commit
                            context.loop_state.current_safe_revision = last_commit
                            context.loop_state.last_commit_hash = last_commit
                            if context.runtime.allow_push and self.git.remote_url(context.paths.repo_dir, "origin"):
                                self.git.push(context.paths.repo_dir, context.metadata.branch)
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
                        "rollback_status": rollback_status if step.status != "completed" else "not_needed",
                        "changed_files": changed_files,
                        "test_results": group_test_result.to_dict() if group_test_result and step.status == "completed" else None,
                    }
                )
                block_entry.update(
                    {
                        "repository_id": context.metadata.repo_id,
                        "repository_slug": context.metadata.slug,
                        "block_index": next_block_index,
                        "status": "completed" if step.status == "completed" else "failed",
                        "selected_task": step.title,
                        "changed_files": changed_files,
                        "test_summary": step.notes or batch_summary,
                        "commit_hashes": [step.commit_hash] if step.commit_hash else [],
                        "rollback_status": rollback_status if step.status != "completed" else "not_needed",
                    }
                )
                reporter.log_pass(pass_entry)
                reporter.log_block(block_entry)
                reporter.append_attempt_history(
                    attempt_history_entry(
                        next_block_index,
                        step.title,
                        "completed" if step.status == "completed" else "parallel batch failed",
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
            if final_status != "completed":
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

    def _normalize_execution_mode(self, value: str | None) -> str:
        normalized = str(value or "").strip().lower()
        return "parallel" if normalized == "parallel" else "serial"

    def _parallel_worker_count(self, value: object) -> int:
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError):
            return 2
        return max(1, min(parsed, 8))

    def _parallel_worker_slug(self, step: ExecutionStep, worker_index: int) -> str:
        raw = f"{worker_index:02d}-{step.step_id.strip().lower() or 'step'}"
        return "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in raw).strip("-") or f"worker-{worker_index:02d}"

    def _build_parallel_worker_runtime(
        self,
        runtime: RuntimeOptions,
        step: ExecutionStep,
    ) -> RuntimeOptions:
        fallback_effort = normalize_reasoning_effort(runtime.effort, fallback="high")
        return RuntimeOptions(
            **{
                **runtime.to_dict(),
                "test_cmd": step.test_command.strip() or runtime.test_cmd,
                "effort": normalize_reasoning_effort(step.reasoning_effort, fallback=fallback_effort),
                "execution_mode": "serial",
                "parallel_workers": 1,
                "max_blocks": 1,
                "allow_push": False,
                "require_checkpoint_approval": False,
                "checkpoint_interval_blocks": 1,
            }
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
        logs_dir = worker_root / "logs"
        reports_dir = worker_root / "reports"
        state_dir = worker_root / "state"
        for directory in [worker_root, docs_dir, memory_dir, logs_dir, reports_dir, state_dir]:
            ensure_dir(directory)
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
            ml_mode_state_file=state_dir / "ML_MODE_STATE.json",
            ml_step_report_file=state_dir / "ML_STEP_REPORT.json",
            ml_experiment_reports_dir=state_dir / "ml_experiments",
            ui_control_file=state_dir / "UI_RUN_CONTROL.json",
            ui_event_log_file=logs_dir / "ui_events.jsonl",
            execution_flow_svg_file=docs_dir / "EXECUTION_FLOW.svg",
            closeout_report_file=docs_dir / "CLOSEOUT_REPORT.md",
            closeout_report_docx_file=reports_dir / "CLOSEOUT_REPORT.docx",
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
            shutil.rmtree(worker_root, ignore_errors=True)

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
            raise RuntimeError("Closeout is already running.")

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
        prompt = finalization_prompt(
            context=context,
            plan_state=plan_state,
            repo_inputs=repo_inputs,
        )
        safe_revision = context.metadata.current_safe_revision or self.git.current_revision(context.paths.repo_dir)
        latest_logged_block = read_last_jsonl(context.paths.block_log_file)
        latest_logged_block_index = int(latest_logged_block.get("block_index", 0)) if latest_logged_block else 0
        closeout_block_index = max(1, context.loop_state.block_index + 1, latest_logged_block_index + 1)
        closeout_task = "Project closeout"
        run_result = runner.run_pass(
            context=context,
            prompt=prompt,
            pass_type="project-closeout-pass",
            block_index=closeout_block_index,
            search_enabled=False,
        )
        run_result.changed_files = self.git.changed_files(context.paths.repo_dir)

        commit_hash: str | None = None
        rollback_status = "not_needed"
        test_result: TestRunResult | None = None
        changed_files = sorted(set(run_result.changed_files))

        try:
            if run_result.returncode != 0:
                self.git.hard_reset(context.paths.repo_dir, safe_revision)
                rollback_status = "rolled_back_to_safe_revision"
                plan_state.closeout_status = "failed"
                plan_state.closeout_notes = "Closeout Codex pass failed and changes were rolled back."
            else:
                test_result = self._run_test_command(context, closeout_block_index, "project-closeout-pass")
                reporter.save_test_result(closeout_block_index, "project-closeout-pass", test_result)
                if test_result.returncode != 0:
                    self.git.hard_reset(context.paths.repo_dir, safe_revision)
                    rollback_status = "rolled_back_to_safe_revision"
                    test_result = None
                    plan_state.closeout_status = "failed"
                    plan_state.closeout_notes = "Closeout verification failed and changes were rolled back."
                else:
                    if self.git.has_changes(context.paths.repo_dir):
                        commit_hash = self.git.commit_all(
                            context.paths.repo_dir,
                            self._commit_message(closeout_block_index, "project-closeout-pass", closeout_task),
                        )
                    if commit_hash:
                        context.metadata.current_safe_revision = commit_hash
                        context.loop_state.current_safe_revision = commit_hash
                        if context.runtime.allow_push and self.git.remote_url(context.paths.repo_dir, "origin"):
                            self.git.push(context.paths.repo_dir, context.metadata.branch)
                    plan_state.closeout_status = "completed"
                    plan_state.closeout_completed_at = now_utc_iso()
                    plan_state.closeout_commit_hash = commit_hash
                    plan_state.closeout_notes = test_result.summary
        except Exception as exc:
            plan_state.closeout_status = "failed"
            plan_state.closeout_notes = str(exc).strip() or "Closeout failed."
            raise
        finally:
            reporter.log_pass(
                {
                    "repository_id": context.metadata.repo_id,
                    "repository_slug": context.metadata.slug,
                    "block_index": closeout_block_index,
                    "pass_type": "project-closeout-pass",
                    "selected_task": closeout_task,
                    "changed_files": changed_files,
                    "test_results": test_result.to_dict() if test_result else None,
                    "usage": run_result.usage,
                    "duration_seconds": run_result.duration_seconds,
                    "codex_attempt_count": run_result.attempt_count,
                    "codex_diagnostics": run_result.diagnostics,
                    "codex_return_code": run_result.returncode,
                    "commit_hash": commit_hash,
                    "rollback_status": rollback_status,
                    "search_enabled": False,
                }
            )
            reporter.log_block(
                {
                    "repository_id": context.metadata.repo_id,
                    "repository_slug": context.metadata.slug,
                    "block_index": closeout_block_index,
                    "status": "closeout_completed" if plan_state.closeout_status == "completed" else "closeout_failed",
                    "selected_task": closeout_task,
                    "changed_files": changed_files,
                    "test_summary": plan_state.closeout_notes,
                    "commit_hashes": [commit_hash] if commit_hash else [],
                    "rollback_status": rollback_status,
                }
            )
            reporter.write_block_review(
                reflection_markdown(closeout_task, plan_state.closeout_notes or "No closeout summary recorded.", changed_files, [commit_hash] if commit_hash else [])
            )
            reporter.append_attempt_history(
                attempt_history_entry(
                    closeout_block_index,
                    closeout_task,
                    "closeout completed" if plan_state.closeout_status == "completed" else "closeout failed",
                    [commit_hash] if commit_hash else [],
                )
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
            if plan_state.closeout_status != "completed":
                self._report_failure(
                    context,
                    reporter,
                    failure_type="closeout_failed",
                    summary=plan_state.closeout_notes or "Closeout failed.",
                    block_index=closeout_block_index,
                    selected_task=closeout_task,
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
        remote_url = self.git.remote_url(context.paths.repo_dir, "origin")
        if push and context.runtime.allow_push and remote_url:
            self.git.push(context.paths.repo_dir, context.metadata.branch)
            target["pushed"] = True
        else:
            target["pushed"] = False
            if not push:
                target["push_skipped_reason"] = "not_requested"
            elif not context.runtime.allow_push:
                target["push_skipped_reason"] = "push_disabled"
            elif not remote_url:
                target["push_skipped_reason"] = "missing_remote"
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

    def _default_ml_mode_state(self, context: ProjectContext) -> MLModeState:
        return MLModeState(
            workflow_mode=normalize_workflow_mode(context.runtime.workflow_mode),
            max_cycles=max(1, int(context.runtime.ml_max_cycles or 1)),
            updated_at=now_utc_iso(),
        )

    def load_ml_mode_state(self, context: ProjectContext) -> MLModeState:
        payload = read_json(context.paths.ml_mode_state_file, default=None)
        if not isinstance(payload, dict):
            return self._default_ml_mode_state(context)
        state = MLModeState.from_dict(payload)
        state.workflow_mode = normalize_workflow_mode(state.workflow_mode or context.runtime.workflow_mode)
        state.max_cycles = max(1, int(state.max_cycles or context.runtime.ml_max_cycles or 1))
        return state

    def _save_ml_mode_state(self, context: ProjectContext, state: MLModeState) -> MLModeState:
        normalized = MLModeState.from_dict(
            {
                **state.to_dict(),
                "workflow_mode": normalize_workflow_mode(state.workflow_mode or context.runtime.workflow_mode),
                "max_cycles": max(1, int(state.max_cycles or context.runtime.ml_max_cycles or 1)),
                "updated_at": now_utc_iso(),
            }
        )
        write_json(context.paths.ml_mode_state_file, normalized.to_dict())
        return normalized

    def _suggest_ml_cycle_index(self, context: ProjectContext, previous_plan_state: ExecutionPlanState | None = None) -> int:
        if normalize_workflow_mode(context.runtime.workflow_mode) != "ml":
            return 0
        state = self.load_ml_mode_state(context)
        if state.cycle_index <= 0:
            return 1
        if previous_plan_state and previous_plan_state.closeout_status == "completed":
            return state.cycle_index + 1
        return state.cycle_index

    def _initialize_ml_mode_state(
        self,
        context: ProjectContext,
        plan_state: ExecutionPlanState,
        objective: str,
        *,
        cycle_index: int,
    ) -> MLModeState:
        state = self.load_ml_mode_state(context)
        state.workflow_mode = normalize_workflow_mode(plan_state.workflow_mode or context.runtime.workflow_mode)
        state.max_cycles = max(1, int(context.runtime.ml_max_cycles or state.max_cycles or 1))
        if state.workflow_mode != "ml":
            return self._save_ml_mode_state(context, state)
        state.objective = objective.strip() or state.objective
        state.cycle_index = max(1, cycle_index or state.cycle_index or 1)
        state.stop_requested = False
        state.stop_reason = ""
        state.replan_required = False
        state.next_cycle_prompt = ""
        if not state.target_metric:
            for step in plan_state.steps:
                if isinstance(step.metadata, dict) and str(step.metadata.get("primary_metric", "")).strip():
                    state.target_metric = str(step.metadata.get("primary_metric", "")).strip()
                    break
        return self._save_ml_mode_state(context, state)

    def _load_ml_experiment_records(self, context: ProjectContext) -> list[MLExperimentRecord]:
        records: list[MLExperimentRecord] = []
        if not context.paths.ml_experiment_reports_dir.exists():
            return records
        for path in sorted(context.paths.ml_experiment_reports_dir.glob("*.json")):
            payload = read_json(path, default=None)
            if not isinstance(payload, dict):
                continue
            record = MLExperimentRecord.from_dict(payload)
            if not record.report_path:
                record.report_path = str(path)
            records.append(record)
        return records

    def _select_best_ml_experiment(self, state: MLModeState, records: list[MLExperimentRecord]) -> MLExperimentRecord | None:
        preferred_metric = state.target_metric.strip()
        matching = [
            record
            for record in records
            if record.metric_value is not None and (not preferred_metric or record.primary_metric == preferred_metric)
        ]
        candidates = matching if matching else [record for record in records if record.metric_value is not None]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda record: record.metric_value if record.metric_direction != "minimize" else -record.metric_value,
        )

    def _ml_results_svg(self, records: list[MLExperimentRecord]) -> str:
        numeric = [record for record in records if record.metric_value is not None]
        if not numeric:
            return (
                '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="180" viewBox="0 0 960 180" role="img">'
                '<rect width="100%" height="100%" fill="#f8fafc" />'
                '<text x="40" y="80" fill="#0f172a" font-family="Segoe UI, Malgun Gothic, sans-serif" font-size="24" font-weight="700">ML experiment results</text>'
                '<text x="40" y="120" fill="#475569" font-family="Segoe UI, Malgun Gothic, sans-serif" font-size="16">No numeric experiment metrics recorded yet.</text>'
                "</svg>"
            )
        width = 960
        row_height = 42
        margin_x = 40
        margin_y = 52
        chart_width = 560
        height = margin_y + len(numeric) * row_height + 40
        values = [float(record.metric_value or 0.0) for record in numeric]
        min_value = min(values)
        max_value = max(values)
        span = max(max_value - min_value, 1e-9)
        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">',
            '<rect width="100%" height="100%" fill="#f8fafc" />',
            f'<text x="{margin_x}" y="30" fill="#0f172a" font-family="Segoe UI, Malgun Gothic, sans-serif" font-size="24" font-weight="700">ML experiment results</text>',
        ]
        for index, record in enumerate(numeric):
            y = margin_y + index * row_height
            value = float(record.metric_value or 0.0)
            normalized = 0.15 + 0.85 * ((value - min_value) / span if span else 1.0)
            bar_width = chart_width * normalized
            label = f"{record.step_id or record.experiment_id}: {record.primary_metric or 'metric'}"
            parts.extend(
                [
                    f'<text x="{margin_x}" y="{y + 18}" fill="#0f172a" font-family="Segoe UI, Malgun Gothic, sans-serif" font-size="13">{escape(label)}</text>',
                    f'<rect x="{margin_x}" y="{y + 24}" rx="8" ry="8" width="{chart_width}" height="12" fill="#e2e8f0" />',
                    f'<rect x="{margin_x}" y="{y + 24}" rx="8" ry="8" width="{bar_width:.1f}" height="12" fill="#2563eb" />',
                    f'<text x="{margin_x + chart_width + 20}" y="{y + 35}" fill="#0f172a" font-family="Segoe UI, Malgun Gothic, sans-serif" font-size="12">{value:.6g}</text>',
                ]
            )
        parts.append("</svg>")
        return "\n".join(parts)

    def _ml_experiment_markdown(self, state: MLModeState, records: list[MLExperimentRecord]) -> str:
        lines = [
            "# ML Experiment Report",
            "",
            f"- Updated at: {now_utc_iso()}",
            f"- Workflow mode: {state.workflow_mode}",
            f"- Cycle index: {state.cycle_index}",
            f"- Max cycles: {state.max_cycles}",
            f"- Objective: {state.objective or 'Not recorded.'}",
            f"- Target metric: {state.target_metric or 'Not recorded.'}",
            f"- Stop requested: {'yes' if state.stop_requested else 'no'}",
            f"- Stop reason: {state.stop_reason or 'continue'}",
            f"- Next cycle prompt: {compact_text(state.next_cycle_prompt, 400) or 'Not recorded.'}",
            "",
            "## Best Result",
            f"- Experiment: {state.best_experiment_id or 'Not recorded.'}",
            f"- Metric: {state.best_metric_name or 'Not recorded.'}",
            f"- Value: {state.best_metric_value if state.best_metric_value is not None else 'Not recorded.'}",
            "",
            "## Experiments",
            "",
            "| Step | Experiment | Kind | Metric | Value | Status | Resources | Notes |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        if not records:
            lines.append("| - | - | - | - | - | - | - | No experiment reports recorded yet. |")
        for record in records:
            lines.append(
                "| {step} | {experiment} | {kind} | {metric} | {value} | {status} | {resources} | {notes} |".format(
                    step=record.step_id or "-",
                    experiment=record.experiment_id or "-",
                    kind=record.experiment_kind or "-",
                    metric=record.primary_metric or "-",
                    value=f"{record.metric_value:.6g}" if record.metric_value is not None else "-",
                    status=record.status or "-",
                    resources=compact_text(record.resource_budget or "-", 80).replace("|", "/"),
                    notes=compact_text(record.notes or record.validation_summary or "-", 120).replace("|", "/"),
                )
            )
        lines.extend(
            [
                "",
                "## Visualization",
                "- See docs/ML_EXPERIMENT_RESULTS.svg for the latest bar-chart summary.",
                "",
            ]
        )
        return "\n".join(lines)

    def refresh_ml_mode_outputs(self, context: ProjectContext) -> MLModeState:
        state = self.load_ml_mode_state(context)
        state.workflow_mode = normalize_workflow_mode(state.workflow_mode or context.runtime.workflow_mode)
        records = self._load_ml_experiment_records(context)
        state.experiments = records
        best = self._select_best_ml_experiment(state, records)
        if best is not None:
            state.best_experiment_id = best.experiment_id
            state.best_metric_name = best.primary_metric
            state.best_metric_value = best.metric_value
        elif not records:
            state.best_experiment_id = ""
            state.best_metric_name = ""
            state.best_metric_value = None
        if state.cycle_index <= 0:
            state.cycle_index = max([record.cycle_index for record in records], default=0)
        write_text(context.paths.ml_experiment_report_file, self._ml_experiment_markdown(state, records))
        write_text(context.paths.ml_experiment_results_svg_file, self._ml_results_svg(records))
        return self._save_ml_mode_state(context, state)

    def _collect_ml_step_report(
        self,
        context: ProjectContext,
        step: ExecutionStep,
        *,
        source_paths: ProjectPaths | None = None,
        report_payload: dict[str, object] | None = None,
    ) -> MLExperimentRecord | None:
        if normalize_workflow_mode(context.runtime.workflow_mode) != "ml":
            return None
        payload = report_payload if isinstance(report_payload, dict) else read_json((source_paths or context.paths).ml_step_report_file, default={})
        if not isinstance(payload, dict):
            payload = {}
        state = self.load_ml_mode_state(context)
        metadata = step.metadata if isinstance(step.metadata, dict) else {}
        destination = context.paths.ml_experiment_reports_dir / f"{step.step_id}.json"
        merged = {
            "experiment_id": payload.get("experiment_id") or metadata.get("experiment_id") or step.step_id,
            "cycle_index": payload.get("cycle_index") or max(1, state.cycle_index or 1),
            "step_id": step.step_id,
            "status": payload.get("status") or step.status or "completed",
            "title": payload.get("title") or step.title,
            "experiment_kind": payload.get("experiment_kind") or metadata.get("experiment_kind", ""),
            "dataset_policy": payload.get("dataset_policy") or metadata.get("dataset_policy", ""),
            "leakage_guard": payload.get("leakage_guard") or metadata.get("leakage_guard", ""),
            "feature_spec": payload.get("feature_spec") or metadata.get("feature_spec", ""),
            "model_spec": payload.get("model_spec") or metadata.get("model_spec", ""),
            "architecture_spec": payload.get("architecture_spec") or metadata.get("architecture_spec", ""),
            "parameter_budget": payload.get("parameter_budget") or metadata.get("parameter_budget", ""),
            "resource_budget": payload.get("resource_budget") or metadata.get("resource_budget", ""),
            "train_command": payload.get("train_command") or metadata.get("train_command", ""),
            "eval_command": payload.get("eval_command") or metadata.get("eval_command", ""),
            "primary_metric": payload.get("primary_metric") or metadata.get("primary_metric", ""),
            "metric_direction": payload.get("metric_direction") or metadata.get("metric_direction", "maximize"),
            "metric_value": payload.get("metric_value"),
            "validation_summary": payload.get("validation_summary") or step.notes,
            "artifact_paths": payload.get("artifact_paths") or metadata.get("artifact_paths", []),
            "notes": payload.get("notes") or step.notes,
            "report_path": str(destination),
            "updated_at": now_utc_iso(),
        }
        record = MLExperimentRecord.from_dict(merged)
        write_json(destination, record.to_dict())
        if source_paths is None or source_paths == context.paths:
            try:
                context.paths.ml_step_report_file.unlink(missing_ok=True)
            except OSError:
                pass
        self.refresh_ml_mode_outputs(context)
        return record

    def should_continue_ml_cycles(self, context: ProjectContext) -> tuple[bool, str]:
        if normalize_workflow_mode(context.runtime.workflow_mode) != "ml":
            return False, "workflow_mode_not_ml"
        state = self.refresh_ml_mode_outputs(context)
        if state.stop_requested:
            return False, state.stop_reason or "ml_stop_requested"
        if state.cycle_index >= max(1, int(context.runtime.ml_max_cycles or 1)):
            state.stop_requested = True
            state.stop_reason = "ml_max_cycles_reached"
            self._save_ml_mode_state(context, state)
            return False, state.stop_reason
        if not state.next_cycle_prompt.strip():
            return False, "next_cycle_prompt_missing"
        return True, ""

    def prepare_next_ml_cycle(
        self,
        project_dir: Path,
        runtime: RuntimeOptions,
        branch: str = "main",
        origin_url: str = "",
    ) -> tuple[ProjectContext, ExecutionPlanState, bool, str]:
        context = self.setup_local_project(project_dir=project_dir, runtime=runtime, branch=branch, origin_url=origin_url)
        current_plan = self.load_execution_plan_state(context)
        should_continue, reason = self.should_continue_ml_cycles(context)
        if not should_continue:
            return context, current_plan, False, reason
        state = self.load_ml_mode_state(context)
        project_prompt = state.next_cycle_prompt.strip()
        if not project_prompt:
            return context, current_plan, False, "next_cycle_prompt_missing"
        context, plan_state = self.generate_execution_plan(
            project_dir=project_dir,
            runtime=runtime,
            project_prompt=project_prompt,
            branch=branch,
            max_steps=max(1, runtime.max_blocks),
            origin_url=origin_url,
        )
        state = self.load_ml_mode_state(context)
        state.replan_required = False
        state.next_cycle_prompt = ""
        state.stop_requested = False
        state.stop_reason = ""
        self._save_ml_mode_state(context, state)
        return context, plan_state, True, ""

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
        metadata_hint = ""
        if step.metadata:
            metadata_hint = f" Metadata: {json.dumps(step.metadata, ensure_ascii=False, sort_keys=True)}."
        if ui_hint and ui_hint != details:
            return f"UI description: {ui_hint}. Execution instruction: {details}.{dependency_hint}{ownership_hint}{metadata_hint} Verification command: {test_command}. Success criteria: {success}"
        return f"{details}.{dependency_hint}{ownership_hint}{metadata_hint} Verification command: {test_command}. Success criteria: {success}"

    def _all_steps_completed(self, steps: list[ExecutionStep]) -> bool:
        return bool(steps) and all(step.status == "completed" for step in steps)

    def _normalize_execution_mode(self, value: str | None) -> str:
        normalized = str(value or "").strip().lower()
        if normalized == "parallel":
            return "parallel"
        return "serial"

    def _status_from_plan_state(self, plan_state: ExecutionPlanState) -> str:
        if not plan_state.steps:
            return "setup_ready"
        if not self._all_steps_completed(plan_state.steps):
            return "plan_ready"
        if plan_state.closeout_status == "completed":
            return "closed_out"
        if plan_state.closeout_status == "running":
            return "running:closeout"
        if plan_state.closeout_status == "failed":
            return "closeout_failed"
        return "plan_completed"

    def _checkpoints_from_execution_steps(self, steps: list[ExecutionStep]) -> list[Checkpoint]:
        checkpoints: list[Checkpoint] = []
        for index, step in enumerate(steps, start=1):
            status = "pending"
            if step.status == "completed":
                status = "approved"
            elif step.status == "running":
                status = "awaiting_review"
            elif step.status in {"failed", "paused"}:
                status = step.status
            checkpoints.append(
                Checkpoint(
                    checkpoint_id=f"CP{index}",
                    title=step.title,
                    plan_refs=[step.step_id],
                    target_block=index,
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
            context.loop_state.counters.regression_failures += 1
            context.loop_state.stop_reason = self._stop_reason(context)
            memory.record_failure(
                task=selected_task,
                summary="Search-enabled Codex pass regressed tests and was rolled back.",
                tags=["search", "regression"],
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
                    "test_summary": "search regression failure",
                    "commit_hashes": [],
                    "rollback_status": "rolled_back_to_safe_revision",
                }
            )
            if not suppress_failure_reporting:
                self._report_failure(
                    context,
                    reporter,
                    failure_type="block_failed",
                    summary="Search-enabled Codex pass regressed tests and was rolled back.",
                    block_index=block_index,
                    selected_task=selected_task,
                )
            return
        if search_commit:
            block_commit_hashes.append(search_commit)
            context.metadata.current_safe_revision = search_commit
            context.loop_state.current_safe_revision = search_commit

        if context.runtime.allow_push and block_commit_hashes and self.git.remote_url(context.paths.repo_dir, "origin"):
            self.git.push(context.paths.repo_dir, context.metadata.branch)

        made_progress = bool(block_commit_hashes)
        if made_progress:
            context.loop_state.counters.no_progress_blocks = 0
            context.loop_state.counters.empty_cycles = 0
        else:
            context.loop_state.counters.no_progress_blocks += 1
            context.loop_state.counters.empty_cycles += 1

        test_summary = search_tests.summary if search_tests else "No search-enabled test run."
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

    def _debug_pass_name(self, pass_name: str) -> str:
        normalized = str(pass_name).strip() or "debug"
        if normalized.endswith("-pass"):
            return f"{normalized[:-5]}-debug"
        return f"{normalized}-debug"

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
            run_result = runner.run_pass(
                context=context,
                prompt=prompt,
                pass_type=debug_pass_name,
                block_index=block_index,
                search_enabled=False,
            )
            run_result.changed_files = self.git.changed_files(context.paths.repo_dir)
            if run_result.returncode != 0:
                return debug_pass_name, run_result, None, None

            test_result = self._run_test_command(context, block_index, debug_pass_name)
            test_result.summary = f"{test_result.summary} after debugger recovery"
            reporter.save_test_result(block_index, debug_pass_name, test_result)
            commit_hash: str | None = None
            if test_result.returncode == 0 and self.git.has_changes(context.paths.repo_dir):
                commit_hash = self.git.commit_all(
                    context.paths.repo_dir,
                    self._commit_message(block_index, debug_pass_name, candidate.title),
                )
            return debug_pass_name, run_result, test_result, commit_hash
        finally:
            context.metadata.last_run_at = now_utc_iso()
            if context.metadata.current_status == "running:debugging":
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
        )

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
        run_result = runner.run_pass(
            context=context,
            prompt=prompt,
            pass_type=pass_name,
            block_index=block_index,
            search_enabled=search_enabled,
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

        test_result = self._run_test_command(context, block_index, pass_name)
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
            commit_hash = self.git.commit_all(
                context.paths.repo_dir,
                self._commit_message(block_index, pass_name, candidate.title),
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

    def _commit_message(self, block_index: int, pass_name: str, task: str) -> str:
        safe_task = " ".join(task.split())[:72]
        return f"jakal-flow(block {block_index} {pass_name}): {safe_task}"

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

    def _parallel_conflict_details(self, conflicted_files: list[str]) -> dict[str, object]:
        files = sorted({str(item).strip() for item in conflicted_files if str(item).strip()})
        return {
            "policy": "abort_and_report",
            "recommended_action": "manual_review",
            "files": files,
            "procedure": (
                "Keep the base branch safe revision, inspect each conflicted file manually, choose the final code intentionally, "
                "then rerun the batch after the overlap is resolved."
            ),
        }

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
        result = runner.run_pass(
            context=context,
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
        result = runner.run_pass(
            context=context,
            prompt=prompt,
            pass_type="plan-work-breakdown",
            block_index=max(0, context.loop_state.block_index),
            search_enabled=False,
        )
        if result.returncode != 0:
            return []
        return parse_work_breakdown_response(result.last_message or "", limit=max_items)
