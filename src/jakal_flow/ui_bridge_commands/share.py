from __future__ import annotations

from .context import BridgeCommandContext, BridgeCommandHandler
from ..share import (
    DEFAULT_SHARE_HOST,
    DEFAULT_SHARE_PORT,
    DEFAULT_SHARE_PUBLIC_BASE_URL,
    DEFAULT_SHARE_TTL_MINUTES,
    ShareServerConfig,
    create_share_session,
    public_session_summary,
    revoke_share_session,
    share_server_status_payload,
)


def build_share_command_handlers(
    *,
    resolve_project,
    coerce_positive_int,
    append_ui_event,
    start_share_server_process,
    stop_share_server_process,
    start_public_tunnel,
    stop_public_tunnel,
    save_share_server_config,
) -> dict[str, BridgeCommandHandler]:
    def save_share_config(ctx: BridgeCommandContext) -> dict:
        config = save_share_server_config(
            ctx.workspace_root,
            ShareServerConfig(
                bind_host=str(ctx.payload.get("bind_host", DEFAULT_SHARE_HOST)).strip() or DEFAULT_SHARE_HOST,
                preferred_port=coerce_positive_int(
                    ctx.payload.get("preferred_port", DEFAULT_SHARE_PORT),
                    default=DEFAULT_SHARE_PORT,
                    minimum=0,
                ),
                public_base_url=str(ctx.payload.get("public_base_url", DEFAULT_SHARE_PUBLIC_BASE_URL)).strip(),
            ),
        )
        result = share_server_status_payload(ctx.workspace_root)
        result["config"] = config.to_dict()
        return result

    def start_share_server(ctx: BridgeCommandContext) -> dict:
        host = str(ctx.payload.get("host", "")).strip() or None
        port = (
            coerce_positive_int(ctx.payload.get("port", DEFAULT_SHARE_PORT), default=DEFAULT_SHARE_PORT, minimum=0)
            if "port" in ctx.payload
            else None
        )
        public_base_url = str(ctx.payload.get("public_base_url", "")).strip() if "public_base_url" in ctx.payload else None
        return start_share_server_process(ctx.workspace_root, host=host, port=port, public_base_url=public_base_url)

    def start_public_share_tunnel(ctx: BridgeCommandContext) -> dict:
        target_url = str(ctx.payload.get("target_url", "")).strip()
        if not target_url:
            status = share_server_status_payload(ctx.workspace_root)
            target_url = str(status.get("base_url") or "").strip()
        return start_public_tunnel(ctx.workspace_root, target_url)

    def create_share(ctx: BridgeCommandContext) -> dict:
        project = resolve_project(ctx.orchestrator, ctx.payload)
        expires_in_minutes = coerce_positive_int(
            ctx.payload.get("expires_in_minutes", DEFAULT_SHARE_TTL_MINUTES),
            default=DEFAULT_SHARE_TTL_MINUTES,
        )
        bind_host = str(ctx.payload.get("bind_host", "")).strip() or None
        preferred_port = (
            coerce_positive_int(ctx.payload.get("preferred_port", DEFAULT_SHARE_PORT), default=DEFAULT_SHARE_PORT, minimum=0)
            if "preferred_port" in ctx.payload
            else None
        )
        public_base_url = str(ctx.payload.get("public_base_url", "")).strip() if "public_base_url" in ctx.payload else None
        share_status = start_share_server_process(
            ctx.workspace_root,
            host=bind_host,
            port=preferred_port,
            public_base_url=public_base_url,
        )
        effective_bind_host = str(share_status.get("config", {}).get("bind_host", bind_host or "")).strip() or bind_host or ""
        should_start_quick_tunnel = (
            effective_bind_host == "0.0.0.0"
            and not public_base_url
            and bool(share_status.get("base_url"))
        )
        quick_tunnel_warning = ""
        if should_start_quick_tunnel:
            try:
                start_public_tunnel(ctx.workspace_root, str(share_status["base_url"]))
            except Exception as exc:
                quick_tunnel_warning = str(exc).strip()
                append_ui_event(
                    project,
                    "share-tunnel-warning",
                    "Automatic public tunnel startup failed; the share session was created without a public URL.",
                    {"error": quick_tunnel_warning},
                )
        elif public_base_url or effective_bind_host != "0.0.0.0":
            stop_public_tunnel(ctx.workspace_root)
        session = create_share_session(
            project,
            expires_in_minutes=expires_in_minutes,
            created_by=str(ctx.payload.get("created_by", "desktop-ui")).strip() or "desktop-ui",
        )
        append_ui_event(
            project,
            "share-session-created",
            "Created a temporary read-only share session.",
            {"session_id": session.session_id, "expires_at": session.expires_at},
        )
        detail = ctx.detail_payload(project)
        detail["created_share_session"] = public_session_summary(ctx.workspace_root, project, session, include_token=True)
        if quick_tunnel_warning:
            detail["share_tunnel_warning"] = quick_tunnel_warning
        return detail

    def revoke_share(ctx: BridgeCommandContext) -> dict:
        project = resolve_project(ctx.orchestrator, ctx.payload)
        session_id = str(ctx.payload.get("session_id", "")).strip()
        if not session_id:
            raise ValueError("session_id is required.")
        session = revoke_share_session(project, session_id)
        append_ui_event(
            project,
            "share-session-revoked",
            "Revoked a temporary read-only share session.",
            {"session_id": session.session_id},
        )
        detail = ctx.detail_payload(project)
        detail["revoked_share_session"] = public_session_summary(ctx.workspace_root, project, session, include_token=False)
        return detail

    return {
        "save_share_server_config": save_share_config,
        "start_share_server": start_share_server,
        "stop_share_server": lambda ctx: stop_share_server_process(ctx.workspace_root),
        "start_public_tunnel": start_public_share_tunnel,
        "stop_public_tunnel": lambda ctx: stop_public_tunnel(ctx.workspace_root),
        "create_share_session": create_share,
        "revoke_share_session": revoke_share,
    }

