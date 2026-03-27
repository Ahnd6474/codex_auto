from __future__ import annotations

from .context import BridgeCommandContext, BridgeCommandHandler
from ..models import ExecutionPlanState
from ..ui_bridge_payloads import list_projects_payload


def build_project_command_handlers(
    *,
    resolve_project,
    common_project_inputs,
    parse_plan_state,
    append_ui_event,
    save_run_control,
    default_run_control,
) -> dict[str, BridgeCommandHandler]:
    def delete_project(ctx: BridgeCommandContext) -> dict:
        project = resolve_project(ctx.orchestrator, ctx.payload)
        repo_id = project.metadata.repo_id
        project_dir = str(project.metadata.repo_path)
        display_name = project.metadata.display_name or project.metadata.slug
        archived = ctx.orchestrator.workspace.delete_project(repo_id)
        listing = list_projects_payload(ctx.orchestrator)
        return {
            "archived": {
                "repo_id": repo_id,
                "archive_id": archived.metadata.archive_id or "",
                "project_dir": project_dir,
                "display_name": display_name,
                "archived_at": archived.metadata.archived_at,
            },
            "projects": listing["projects"],
            "history": listing["history"],
            "workspace": listing["workspace"],
        }

    def delete_all_projects(ctx: BridgeCommandContext) -> dict:
        archived = ctx.orchestrator.workspace.delete_all_projects()
        listing = list_projects_payload(ctx.orchestrator)
        return {
            "archived_all": True,
            "archived_count": len(archived),
            "projects": listing["projects"],
            "history": listing["history"],
            "workspace": listing["workspace"],
        }

    def save_project_setup(ctx: BridgeCommandContext) -> dict:
        project_dir, runtime, branch, origin_url, display_name = common_project_inputs(ctx.payload)
        project = ctx.orchestrator.setup_local_project(
            project_dir=project_dir,
            runtime=runtime,
            branch=branch,
            origin_url=origin_url,
            display_name=display_name,
        )
        save_run_control(project, default_run_control())
        append_ui_event(project, "project-saved", "Saved project setup from the desktop shell.")
        return ctx.detail_payload(project)

    def generate_plan(ctx: BridgeCommandContext) -> dict:
        project_dir, runtime, branch, origin_url, _display_name = common_project_inputs(ctx.payload)
        prompt = str(ctx.payload.get("prompt", "")).strip()
        if not prompt:
            raise ValueError("prompt is required.")
        max_steps = max(1, int(str(ctx.payload.get("max_steps", runtime.max_blocks) or runtime.max_blocks)))
        existing = ctx.orchestrator.local_project(project_dir)
        project, plan_state = ctx.orchestrator.generate_execution_plan(
            project_dir=project_dir,
            runtime=runtime,
            project_prompt=prompt,
            branch=branch,
            max_steps=max_steps,
            origin_url=origin_url,
        )
        append_ui_event(
            project,
            "plan-generated",
            f"Generated a new execution plan with {len(plan_state.steps)} step(s).",
            {"max_steps": max_steps},
        )
        if existing is None and ctx.payload.get("display_name"):
            project.metadata.display_name = str(ctx.payload.get("display_name")).strip()
            ctx.orchestrator.workspace.save_project(project)
        return ctx.detail_payload(project)

    def save_plan(ctx: BridgeCommandContext) -> dict:
        project_dir, runtime, branch, origin_url, _display_name = common_project_inputs(ctx.payload)
        raw_plan = ctx.payload.get("plan", {})
        if not isinstance(raw_plan, dict):
            raise ValueError("plan payload must be an object.")
        plan_state = parse_plan_state(raw_plan)
        project, _saved = ctx.orchestrator.update_execution_plan(
            project_dir=project_dir,
            runtime=runtime,
            plan_state=plan_state,
            branch=branch,
            origin_url=origin_url,
        )
        append_ui_event(project, "plan-saved", "Saved the edited execution plan.")
        return ctx.detail_payload(project)

    def reset_plan(ctx: BridgeCommandContext) -> dict:
        project_dir, runtime, branch, origin_url, _display_name = common_project_inputs(ctx.payload)
        plan_state = ExecutionPlanState(default_test_command=runtime.test_cmd)
        project, _saved = ctx.orchestrator.update_execution_plan(
            project_dir=project_dir,
            runtime=runtime,
            plan_state=plan_state,
            branch=branch,
            origin_url=origin_url,
        )
        append_ui_event(project, "plan-reset", "Reset the execution plan and cleared the prompt.")
        return ctx.detail_payload(project)

    return {
        "delete-project": delete_project,
        "delete-all-projects": delete_all_projects,
        "save-project-setup": save_project_setup,
        "generate-plan": generate_plan,
        "save-plan": save_plan,
        "reset-plan": reset_plan,
    }
