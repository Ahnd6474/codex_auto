from __future__ import annotations

from typing import Any

from ..chat_sessions import chat_payload
from ..public_tunnel import public_tunnel_status_payload
from ..share import project_share_payload, share_server_status_payload, workspace_share_payload
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
    resolve_history_project,
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

    def load_history_entry(ctx: BridgeCommandContext) -> dict[str, Any]:
        project = resolve_history_project(ctx.orchestrator, ctx.payload)
        return ctx.detail_payload(
            project,
            refresh_codex_status=False,
            detail_level=str(ctx.payload.get("detail_level", "full")).strip().lower() or "full",
        )

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

    def load_project_chat(ctx: BridgeCommandContext) -> dict[str, Any]:
        project = resolve_project(ctx.orchestrator, ctx.payload)
        session_id = str(ctx.payload.get("session_id", "")).strip()
        return {
            "chat": chat_payload(project, session_id=session_id, activate=True),
            "loaded_sections": {
                "chat": True,
            },
            "emit_project_changed": False,
        }

    return {
        "bootstrap": lambda ctx: bootstrap_payload(ctx.workspace_root),
        "list-projects": lambda ctx: list_projects_payload(ctx.orchestrator),
        "load-project": load_project_detail,
        "load-project-core": load_project_core,
        "load-project-history": load_project_history,
        "load-history-entry": load_history_entry,
        "load-project-reports": load_project_reports,
        "load-project-config": load_project_config,
        "load-project-workspace": load_project_workspace,
        "load-project-checkpoints": load_project_checkpoints,
        "load-project-share": load_project_share,
        "load-project-chat": load_project_chat,
        "load-workspace-share": lambda ctx: {"share": workspace_share_payload(ctx.workspace_root)},
        "get_share_server_status": lambda ctx: share_server_status_payload(ctx.workspace_root),
        "get_public_tunnel_status": lambda ctx: public_tunnel_status_payload(ctx.workspace_root),
    }
