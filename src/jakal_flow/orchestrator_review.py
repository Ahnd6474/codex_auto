from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .errors import HANDLED_OPERATION_EXCEPTIONS, ExecutionFailure
from .execution_control import ImmediateStopRequested
from .models import ExecutionPlanState, ProjectContext, RuntimeOptions
from .model_selection import normalize_reasoning_effort
from .planning import reviewer_a_prompt
from .reporting import Reporter
from .utils import now_utc_iso

UTC = getattr(datetime, "UTC", timezone.utc)


class OrchestratorReviewMixin:
    def _execution_review_is_ready(self, plan_state: ExecutionPlanState) -> bool:
        return (
            str(plan_state.reviewer_a_status or "").strip().lower() == "completed"
            and self._normalize_reviewer_a_verdict(plan_state.reviewer_a_verdict) == "READY_TO_EXECUTE"
            and str(plan_state.reviewer_a_plan_signature or "").strip() == self._plan_review_signature(plan_state)
        )

    def _execution_review_requested_replan(self, plan_state: ExecutionPlanState) -> bool:
        return (
            str(plan_state.reviewer_a_status or "").strip().lower() == "replan_required"
            and bool(str(plan_state.next_cycle_prompt or "").strip())
            and str(plan_state.reviewer_a_plan_signature or "").strip() == self._plan_review_signature(plan_state)
        )

    def _completed_plan_needs_reviewer_a_backfill(self, plan_state: ExecutionPlanState) -> bool:
        return self._all_steps_completed(plan_state.steps) and not self._execution_review_is_ready(plan_state)

    def _resume_pre_execution_replan(
        self,
        *,
        project_dir: Path,
        runtime: RuntimeOptions,
        plan_state: ExecutionPlanState,
        branch: str,
        origin_url: str,
    ) -> tuple[ProjectContext, ExecutionPlanState]:
        next_cycle_prompt = str(plan_state.next_cycle_prompt or "").strip()
        if not next_cycle_prompt:
            raise RuntimeError("Reviewer A requested replanning but did not persist a next-cycle prompt.")
        return self.generate_execution_plan(
            project_dir=project_dir,
            runtime=runtime,
            project_prompt=next_cycle_prompt,
            branch=branch,
            max_steps=max(1, runtime.max_blocks),
            origin_url=origin_url,
        )

    def _reviewer_a_run_is_stale(self, context: ProjectContext, plan_state: ExecutionPlanState) -> bool:
        if str(plan_state.reviewer_a_status or "").strip().lower() != "running":
            return False
        if context.metadata.current_status != "running:reviewer-a":
            return True
        heartbeat = max(
            (
                item
                for item in (
                    self._parse_iso_timestamp(context.metadata.last_run_at),
                    self._parse_iso_timestamp(plan_state.reviewer_a_started_at),
                )
                if item is not None
            ),
            default=None,
        )
        if heartbeat is None:
            return True
        return datetime.now(tz=UTC) - heartbeat > self._STALE_CLOSEOUT_TIMEOUT

    def _recover_stale_reviewer_a_state(self, context: ProjectContext, plan_state: ExecutionPlanState) -> bool:
        if not self._reviewer_a_run_is_stale(context, plan_state):
            return False
        plan_state.reviewer_a_status = "failed"
        plan_state.reviewer_a_completed_at = None
        plan_state.reviewer_a_notes = "Recovered a stale Reviewer A state before retrying."
        plan_state.reviewer_a_verdict = ""
        plan_state.reviewer_a_plan_signature = ""
        plan_state.replan_required = False
        plan_state.next_cycle_prompt = ""
        plan_state.last_updated_at = now_utc_iso()
        context.metadata.current_status = self._status_from_plan_state(plan_state)
        context.metadata.last_run_at = plan_state.last_updated_at
        self.save_execution_plan_state(context, plan_state)
        self.workspace.save_project(context)
        return True

    def run_pre_execution_review(
        self,
        project_dir: Path,
        runtime: RuntimeOptions,
        branch: str = "main",
        origin_url: str = "",
        *,
        allow_completed_plan_backfill: bool = False,
        review_task_name: str = "Reviewer A pre-execution pass",
    ) -> tuple[ProjectContext, ExecutionPlanState]:
        context = self.setup_local_project(project_dir=project_dir, runtime=runtime, branch=branch, origin_url=origin_url)
        plan_state = self.load_execution_plan_state(context)
        if not plan_state.steps:
            raise RuntimeError("No saved execution plan exists for this project.")
        if self._all_steps_completed(plan_state.steps) and not allow_completed_plan_backfill:
            return context, plan_state
        if self._execution_review_requested_replan(plan_state):
            return context, plan_state
        if self._execution_review_is_ready(plan_state):
            return context, plan_state
        if str(plan_state.reviewer_a_status or "").strip().lower() == "running":
            if not self._recover_stale_reviewer_a_state(context, plan_state):
                raise RuntimeError("Reviewer A is already running.")
            plan_state = self.load_execution_plan_state(context)

        previous_runtime = context.runtime
        reviewer_effort = normalize_reasoning_effort(
            getattr(previous_runtime, "planning_effort", ""),
            fallback=normalize_reasoning_effort(previous_runtime.effort, fallback="high"),
        )
        context.runtime = RuntimeOptions(
            **{
                **previous_runtime.to_dict(),
                "effort": reviewer_effort,
                "allow_push": True,
                "approval_mode": runtime.approval_mode,
                "sandbox_mode": runtime.sandbox_mode,
                "require_checkpoint_approval": False,
                "checkpoint_interval_blocks": 1,
            }
        )

        review_started_at = now_utc_iso()
        plan_state.reviewer_a_status = "running"
        plan_state.reviewer_a_started_at = review_started_at
        plan_state.reviewer_a_completed_at = None
        plan_state.reviewer_a_notes = ""
        plan_state.reviewer_a_verdict = ""
        plan_state.reviewer_a_plan_signature = ""
        plan_state.reviewer_b_decision = ""
        plan_state.replan_required = False
        plan_state.next_cycle_prompt = ""
        context.metadata.current_status = "running:reviewer-a"
        context.metadata.last_run_at = review_started_at
        context.loop_state.current_task = review_task_name
        self.save_execution_plan_state(context, plan_state)
        self.workspace.save_project(context)

        reporter = Reporter(context)
        safe_revision = context.metadata.current_safe_revision or self.git.current_revision(context.paths.repo_dir)
        block_index = self._next_logged_block_index(context)
        runner = self._create_codex_runner(context.runtime.codex_path)
        review_result: dict[str, object] = {
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
            repo_inputs = self._scan_repository_inputs(context)
            self._clear_reviewer_a_outputs(context)
            review_result = self._execute_verified_repo_pass(
                context=context,
                runner=runner,
                reporter=reporter,
                prompt=reviewer_a_prompt(context=context, plan_state=plan_state, repo_inputs=repo_inputs),
                pass_type="project-reviewer-a-pass",
                block_index=block_index,
                task_name=review_task_name,
                safe_revision=safe_revision,
                post_test_validation=lambda: self._load_reviewer_a_outputs(context),
            )
            self._record_reviewer_pass(
                context=context,
                reporter=reporter,
                block_index=block_index,
                reviewer_role="A",
                task_name=review_task_name,
                pass_result=review_result,
            )
            if bool(review_result.get("success")):
                verdict = self._normalize_reviewer_a_verdict(review_result.get("reviewer_a_verdict"))
                plan_state.reviewer_a_verdict = verdict
                plan_state.reviewer_a_plan_signature = self._plan_review_signature(plan_state)
                plan_state.reviewer_a_completed_at = now_utc_iso()
                plan_state.reviewer_a_notes = str(review_result.get("notes") or "").strip()
                if verdict == "REPLAN":
                    plan_state.reviewer_a_status = "replan_required"
                    plan_state.replan_required = True
                    plan_state.next_cycle_prompt = str(review_result.get("next_cycle_prompt") or "").strip()
                else:
                    plan_state.reviewer_a_status = "completed"
                    plan_state.replan_required = False
                    plan_state.next_cycle_prompt = ""
            else:
                plan_state.reviewer_a_status = "failed"
                plan_state.reviewer_a_notes = str(review_result.get("notes") or "").strip()
                plan_state.reviewer_a_plan_signature = ""
                plan_state.replan_required = False
                plan_state.next_cycle_prompt = ""
        except ImmediateStopRequested as exc:
            self.git.hard_reset(context.paths.repo_dir, safe_revision)
            plan_state.reviewer_a_status = "not_started"
            plan_state.reviewer_a_started_at = None
            plan_state.reviewer_a_completed_at = None
            plan_state.reviewer_a_notes = str(exc).strip() or "Immediate stop requested."
            plan_state.reviewer_a_verdict = ""
            plan_state.reviewer_a_plan_signature = ""
            plan_state.replan_required = False
            plan_state.next_cycle_prompt = ""
        except HANDLED_OPERATION_EXCEPTIONS as exc:
            plan_state.reviewer_a_status = "failed"
            plan_state.reviewer_a_completed_at = None
            plan_state.reviewer_a_notes = str(exc).strip() or "Reviewer A failed."
            plan_state.reviewer_a_verdict = ""
            plan_state.reviewer_a_plan_signature = ""
            plan_state.replan_required = False
            plan_state.next_cycle_prompt = ""
            raise
        finally:
            context.runtime = previous_runtime
            context.metadata.current_status = self._status_from_plan_state(plan_state)
            context.metadata.last_run_at = now_utc_iso()
            self.save_execution_plan_state(context, plan_state)
            self.workspace.save_project(context)
            reporter.write_status_report()

        return context, plan_state

    def prepare_pre_execution_cycle(
        self,
        project_dir: Path,
        runtime: RuntimeOptions,
        branch: str = "main",
        origin_url: str = "",
    ) -> tuple[ProjectContext, ExecutionPlanState, bool, str]:
        context = self.setup_local_project(project_dir=project_dir, runtime=runtime, branch=branch, origin_url=origin_url)
        current_plan = self.load_execution_plan_state(context)
        if not current_plan.steps:
            return context, current_plan, False, "plan_missing"
        if self._execution_review_requested_replan(current_plan):
            next_context, next_plan = self._resume_pre_execution_replan(
                project_dir=project_dir,
                runtime=runtime,
                plan_state=current_plan,
                branch=branch,
                origin_url=origin_url,
            )
            return next_context, next_plan, True, ""
        if self._execution_review_is_ready(current_plan):
            if self._all_steps_completed(current_plan.steps):
                return context, current_plan, False, "all_steps_completed"
            return context, current_plan, False, "execution_ready"
        if str(current_plan.reviewer_a_status or "").strip().lower() == "running" and not self._reviewer_a_run_is_stale(context, current_plan):
            return context, current_plan, False, "reviewer_a_running"

        completed_plan_backfill = self._completed_plan_needs_reviewer_a_backfill(current_plan)
        review_task_name = (
            "Reviewer A completed-plan backfill"
            if completed_plan_backfill
            else "Reviewer A pre-execution pass"
        )

        context, reviewed_plan = self.run_pre_execution_review(
            project_dir=project_dir,
            runtime=runtime,
            branch=branch,
            origin_url=origin_url,
            allow_completed_plan_backfill=completed_plan_backfill,
            review_task_name=review_task_name,
        )
        if self._execution_review_requested_replan(reviewed_plan):
            next_context, next_plan = self._resume_pre_execution_replan(
                project_dir=project_dir,
                runtime=runtime,
                plan_state=reviewed_plan,
                branch=branch,
                origin_url=origin_url,
            )
            return next_context, next_plan, True, ""
        if self._execution_review_is_ready(reviewed_plan):
            if self._all_steps_completed(reviewed_plan.steps):
                return context, reviewed_plan, False, "all_steps_completed"
            return context, reviewed_plan, False, "execution_ready"
        if str(reviewed_plan.reviewer_a_status or "").strip().lower() == "failed":
            return context, reviewed_plan, False, "reviewer_a_failed"
        return context, reviewed_plan, False, "reviewer_a_blocked"

    def _require_pre_execution_review_ready(
        self,
        project_dir: Path,
        runtime: RuntimeOptions,
        branch: str,
        origin_url: str,
    ) -> tuple[ProjectContext, ExecutionPlanState]:
        context, plan_state, continued, reason = self.prepare_pre_execution_cycle(
            project_dir=project_dir,
            runtime=runtime,
            branch=branch,
            origin_url=origin_url,
        )
        if continued:
            raise RuntimeError("Reviewer A requested replanning before execution. Rerun execution after the new plan is reviewed.")
        if not self._execution_review_is_ready(plan_state):
            raise RuntimeError(f"Execution is blocked until Reviewer A is ready ({reason}).")
        return context, plan_state
