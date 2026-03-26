from __future__ import annotations

from typing import Any

from ..public_tunnel import public_tunnel_status_payload
from ..share import project_share_payload, share_server_status_payload
from ..ui_bridge_payloads import (
    checkpoint_payload,
    config_payload,
    history_payload,
    list_projects_payload,
    managed_workspace_tree,
    report_payload,
)
from .context import BridgeCommandContext, BridgeCommandHandler


def build_read_model_handlers(
    *,
    bootstrap_payload,
    resolve_project,
    coerce_bool,
    codex_snapshot_service,
) -> dict[str, BridgeCommandHandler]:
    def load_project_detail(ctx: BridgeCommandContext) -> dict[str, Any]:
        project = resolve_project(ctx.orchestrator, ctx.payload)
        refresh_codex_status = coerce_bool(ctx.payload.get("refresh_codex_status", True), True)
        if refresh_codex_status:
            codex_snapshot_service.invalidate(project.runtime.codex_path)
        return ctx.detail_payload(
            project,
            refresh_codex_status=refresh_codex_status,
            detail_level=str(ctx.payload.get("detail_level", "full")).strip().lower() or "full",
        )

    def load_project_core(ctx: BridgeCommandContext) -> dict[str, Any]:
        project = resolve_project(ctx.orchestrator, ctx.payload)
        refresh_codex_status = coerce_bool(ctx.payload.get("refresh_codex_status", False), False)
        if refresh_codex_status:
            codex_snapshot_service.invalidate(project.runtime.codex_path)
        return ctx.detail_payload(
            project,
            refresh_codex_status=refresh_codex_status,
            detail_level="core",
        )

    def load_project_history(ctx: BridgeCommandContext) -> dict[str, Any]:
        return history_payload(resolve_project(ctx.orchestrator, ctx.payload))

    def load_project_reports(ctx: BridgeCommandContext) -> dict[str, Any]:
        return report_payload(resolve_project(ctx.orchestrator, ctx.payload))

    def load_project_config(ctx: BridgeCommandContext) -> dict[str, Any]:
        return config_payload(resolve_project(ctx.orchestrator, ctx.payload))

    def load_project_workspace(ctx: BridgeCommandContext) -> dict[str, Any]:
        project = resolve_project(ctx.orchestrator, ctx.payload)
        return {"workspace_tree": managed_workspace_tree(project)}

    def load_project_checkpoints(ctx: BridgeCommandContext) -> dict[str, Any]:
        return checkpoint_payload(resolve_project(ctx.orchestrator, ctx.payload))

    def load_project_share(ctx: BridgeCommandContext) -> dict[str, Any]:
        project = resolve_project(ctx.orchestrator, ctx.payload)
        return {"share": project_share_payload(ctx.orchestrator.workspace.workspace_root, project)}

    return {
        "bootstrap": lambda ctx: bootstrap_payload(ctx.workspace_root),
        "list-projects": lambda ctx: list_projects_payload(ctx.orchestrator),
        "load-project": load_project_detail,
        "load-project-core": load_project_core,
        "load-project-history": load_project_history,
        "load-project-reports": load_project_reports,
        "load-project-config": load_project_config,
        "load-project-workspace": load_project_workspace,
        "load-project-checkpoints": load_project_checkpoints,
        "load-project-share": load_project_share,
        "get_share_server_status": lambda ctx: share_server_status_payload(ctx.workspace_root),
        "get_public_tunnel_status": lambda ctx: public_tunnel_status_payload(ctx.workspace_root),
    }

