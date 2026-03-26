from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import subprocess
import shutil
from pathlib import Path
from uuid import uuid4

from .environment import ensure_gitignore, ensure_virtualenv
from .codex_runner import CodexRunner
from .git_ops import GitOps
from .memory import MemoryStore
from .model_selection import normalize_reasoning_effort
from .models import CandidateTask, Checkpoint, ExecutionPlanState, ExecutionStep, LoopState, ProjectContext, ProjectPaths, RepoMetadata, RuntimeOptions, TestRunResult
from .planning import (
    FINALIZATION_PROMPT_FILENAME,
    PLAN_GENERATION_PROMPT_FILENAME,
    STEP_EXECUTION_PROMPT_FILENAME,
    attempt_history_entry,
    assess_repository_maturity,
    build_mid_term_plan,
    build_mid_term_plan_from_plan_items,
    build_mid_term_plan_from_user_items,
    build_checkpoint_timeline,
    bootstrap_plan_prompt,
    candidate_tasks_from_mid_term,
    checkpoint_timeline_markdown,
    execution_plan_markdown,
    execution_plan_svg,
    execution_steps_to_plan_items,
    finalization_prompt,
    ensure_scope_guard,
    generate_project_plan,
    implementation_prompt,
    is_plan_markdown,
    parse_execution_plan_response,
    parse_work_breakdown_response,
    prompt_to_execution_plan_prompt,
    reflection_markdown,
    scan_repository_inputs,
    select_candidate,
    validate_mid_term_subset,
    work_breakdown_prompt,
    write_active_task,
    load_source_prompt_template,
)
from .reporting import Reporter
from .utils import decode_process_output, ensure_dir, now_utc_iso, read_json, read_last_jsonl, read_text, write_json, write_text
from .workspace import WorkspaceManager


class Orchestrator:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace = WorkspaceManager(workspace_root)
        self.git = GitOps()

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
        planning_prompt_template = load_source_prompt_template(PLAN_GENERATION_PROMPT_FILENAME)
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
            execution_mode=self._normalize_execution_mode(runtime.execution_mode),
            default_test_command=runtime.test_cmd,
            last_updated_at=now_utc_iso(),
            steps=steps,
        )
        self.save_execution_plan_state(context, plan_state)
        context.metadata.current_status = "plan_ready"
        context.metadata.last_run_at = now_utc_iso()
        self.workspace.save_project(context)
        return context, plan_state

    def load_execution_plan_state(self, context: ProjectContext) -> ExecutionPlanState:
        payload = read_json(context.paths.execution_plan_file, default=None)
        if not isinstance(payload, dict):
            return ExecutionPlanState(
                default_test_command=context.runtime.test_cmd,
                last_updated_at=now_utc_iso(),
                steps=[],
            )
        state = ExecutionPlanState.from_dict(payload)
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
        normalized_steps: list[ExecutionStep] = []
        fallback_effort = normalize_reasoning_effort(context.runtime.effort, fallback="high")
        execution_mode = self._normalize_execution_mode(plan_state.execution_mode or context.runtime.execution_mode)
        for index, step in enumerate(plan_state.steps, start=1):
            normalized_steps.append(
                ExecutionStep(
                    step_id=f"ST{index}",
                    title=step.title.strip(),
                    display_description=step.display_description.strip(),
                    codex_description=step.codex_description.strip() or step.display_description.strip() or step.title.strip(),
                    test_command=step.test_command.strip() or plan_state.default_test_command or context.runtime.test_cmd,
                    success_criteria=step.success_criteria.strip(),
                    reasoning_effort=normalize_reasoning_effort(step.reasoning_effort, fallback=fallback_effort),
                    parallel_group=step.parallel_group.strip() if execution_mode == "parallel" else "",
                    status=step.status if step.status else "pending",
                    started_at=step.started_at,
                    completed_at=step.completed_at,
                    commit_hash=step.commit_hash,
                    notes=step.notes.strip(),
                )
            )
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
            execution_plan_markdown(context, state.plan_title, state.project_prompt, state.summary, state.steps),
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
        write_text(context.paths.execution_flow_svg_file, execution_plan_svg(f"{flow_title} execution flow", state.steps))
        return state

    def pending_execution_batches(self, plan_state: ExecutionPlanState) -> list[list[ExecutionStep]]:
        remaining = [step for step in plan_state.steps if step.status != "completed"]
        if not remaining:
            return []
        if self._normalize_execution_mode(plan_state.execution_mode) != "parallel":
            return [[step] for step in remaining]

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

        target_step: ExecutionStep | None = None
        for step in plan_state.steps:
            if step.status == "completed":
                continue
            if step_id and step.step_id != step_id:
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
        previous_block = read_last_jsonl(context.paths.block_log_file)
        previous_block_index = int(previous_block.get("block_index", -1)) if previous_block else -1
        candidate = CandidateTask(
            candidate_id=target_step.step_id,
            title=target_step.title,
            rationale=self._execution_step_rationale(target_step, context.runtime.test_cmd),
            plan_refs=[target_step.step_id],
            score=1.0,
        )
        target_step = next(step for step in plan_state.steps if step.step_id == target_step.step_id)
        try:
            self._run_single_block(
                context=context,
                runner=runner,
                memory=memory,
                reporter=reporter,
                candidate_override=candidate,
                execution_step_override=target_step,
            )
            context.metadata.last_run_at = now_utc_iso()
            latest_block = read_last_jsonl(context.paths.block_log_file)
            latest_block_index = int(latest_block.get("block_index", -1)) if latest_block else -1
            if latest_block_index <= previous_block_index:
                latest_block = None
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
                target_step.notes = str(context.loop_state.stop_reason or "Step execution failed.").strip()
                context.metadata.current_status = "failed"
        except Exception as exc:
            target_step.status = "failed"
            target_step.notes = str(exc).strip() or "Step execution failed."
            context.metadata.current_status = "failed"
            raise
        finally:
            context.runtime = previous_runtime
            self.save_execution_plan_state(context, plan_state)
            self.workspace.save_project(context)

        return context, plan_state, target_step

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
        parallel_groups = {step.parallel_group.strip() for step in ordered_targets}
        if "" in parallel_groups or len(parallel_groups) != 1:
            raise RuntimeError("Parallel execution batch steps must share one non-empty parallel group.")

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
                        self.git.hard_reset(context.paths.repo_dir, base_revision)
                        rollback_status = "rolled_back_to_safe_revision"
                        final_status = "failed"
                        batch_summary = "Parallel batch verification failed and merged changes were rolled back."
                        group_test_result = None
                        for step in ordered_targets:
                            step.status = "failed"
                            step.notes = batch_summary
                        context.metadata.current_status = "failed"
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
            ui_control_file=state_dir / "UI_RUN_CONTROL.json",
            ui_event_log_file=logs_dir / "ui_events.jsonl",
            execution_flow_svg_file=docs_dir / "EXECUTION_FLOW.svg",
            closeout_report_file=docs_dir / "CLOSEOUT_REPORT.md",
            closeout_report_docx_file=reports_dir / "CLOSEOUT_REPORT.docx",
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
            self._run_single_block(
                context=worker_context,
                runner=runner,
                memory=memory,
                reporter=reporter,
                candidate_override=candidate,
                execution_step_override=deepcopy(step),
            )
            latest_block = read_last_jsonl(worker_context.paths.block_log_file) or {}
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
            template_text=load_source_prompt_template(FINALIZATION_PROMPT_FILENAME),
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
        if push and context.metadata.current_safe_revision:
            self.git.push(context.paths.repo_dir, context.metadata.branch)
            target["pushed"] = True
        write_json(context.paths.checkpoint_state_file, data)
        context.loop_state.pending_checkpoint_approval = False
        context.loop_state.stop_requested = False
        context.loop_state.stop_reason = None
        context.metadata.current_status = "ready"
        self.workspace.save_project(context)
        return target

    def request_stop(self, repo_url: str, branch: str) -> dict[str, str]:
        context = self.status(repo_url, branch)
        context.loop_state.stop_requested = True
        context.loop_state.stop_reason = "user stop requested"
        self.workspace.save_project(context)
        return {"status": "stop_requested"}

    def _ensure_project_documents(self, context: ProjectContext) -> None:
        for file_path, starter in [
            (context.paths.active_task_file, "# Active Task\n\nNo active task selected yet.\n"),
            (context.paths.block_review_file, "# Block Review\n\nNo completed blocks yet.\n"),
            (context.paths.research_notes_file, "# Research Notes\n\nNo research notes recorded yet.\n"),
            (context.paths.attempt_history_file, "# Attempt History\n\n"),
            (context.paths.closeout_report_file, "# Closeout Report\n\nNo closeout has been run yet.\n"),
        ]:
            if not file_path.exists():
                write_text(file_path, starter)
        if not context.paths.scope_guard_file.exists():
            write_text(context.paths.scope_guard_file, ensure_scope_guard(context))
        if not context.paths.execution_plan_file.exists():
            write_json(context.paths.execution_plan_file, ExecutionPlanState(default_test_command=context.runtime.test_cmd).to_dict())
        if not context.paths.execution_flow_svg_file.exists():
            write_text(
                context.paths.execution_flow_svg_file,
                execution_plan_svg(f"{context.metadata.display_name or context.metadata.slug} execution flow", []),
            )

    def _execution_step_rationale(self, step: ExecutionStep, test_command: str) -> str:
        details = step.codex_description or step.display_description or "Complete the saved execution checkpoint with a small, safe change."
        success = step.success_criteria or "The verification command exits successfully."
        ui_hint = step.display_description.strip()
        if ui_hint and ui_hint != details:
            return f"UI description: {ui_hint}. Execution instruction: {details} Verification command: {test_command}. Success criteria: {success}"
        return f"{details} Verification command: {test_command}. Success criteria: {success}"

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
        execution_prompt_template = load_source_prompt_template(STEP_EXECUTION_PROMPT_FILENAME)
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
            reporter.log_pass(
                {
                    "repository_id": context.metadata.repo_id,
                    "repository_slug": context.metadata.slug,
                    "block_index": block_index,
                    "pass_type": pass_name,
                    "selected_task": candidate.title,
                    "changed_files": run_result.changed_files,
                    "test_results": None,
                    "usage": run_result.usage,
                    "codex_attempt_count": run_result.attempt_count,
                    "codex_diagnostics": run_result.diagnostics,
                    "codex_return_code": run_result.returncode,
                    "commit_hash": None,
                    "rollback_status": "rolled_back_to_safe_revision",
                    "search_enabled": search_enabled,
                }
            )
            return run_result, None, None

        test_result = self._run_test_command(context, block_index, pass_name)
        reporter.save_test_result(block_index, pass_name, test_result)
        commit_hash: str | None = None
        rollback_status = "not_needed"
        if test_result.returncode != 0:
            self.git.hard_reset(context.paths.repo_dir, safe_revision)
            rollback_status = "rolled_back_to_safe_revision"
            test_result = None
        elif self.git.has_changes(context.paths.repo_dir):
            commit_hash = self.git.commit_all(
                context.paths.repo_dir,
                self._commit_message(block_index, pass_name, candidate.title),
            )
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
                "codex_attempt_count": run_result.attempt_count,
                "codex_diagnostics": run_result.diagnostics,
                "codex_return_code": run_result.returncode,
                "commit_hash": commit_hash,
                "rollback_status": rollback_status,
                "search_enabled": search_enabled,
            }
        )
        return run_result, test_result, commit_hash

    def _run_test_command(self, context: ProjectContext, block_index: int, label: str) -> TestRunResult:
        block_dir = context.paths.logs_dir / f"block_{block_index:04d}"
        stdout_file = block_dir / f"{label}.test.stdout.log"
        stderr_file = block_dir / f"{label}.test.stderr.log"
        completed = subprocess.run(
            context.runtime.test_cmd,
            cwd=context.paths.repo_dir,
            shell=True,
            capture_output=True,
            check=False,
        )
        stdout = decode_process_output(completed.stdout)
        stderr = decode_process_output(completed.stderr)
        write_text(stdout_file, stdout)
        write_text(stderr_file, stderr)
        return TestRunResult(
            command=context.runtime.test_cmd,
            returncode=completed.returncode,
            stdout_file=stdout_file,
            stderr_file=stderr_file,
            summary=f"{context.runtime.test_cmd} exited with {completed.returncode}",
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
