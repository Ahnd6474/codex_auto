from __future__ import annotations

import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import urlopen

from .context import BridgeCommandContext, BridgeCommandHandler
from ..share import (
    DEFAULT_SHARE_HOST,
    DEFAULT_SHARE_PORT,
    DEFAULT_SHARE_PUBLIC_BASE_URL,
    DEFAULT_SHARE_TTL_MINUTES,
    ShareServerConfig,
    create_workspace_share_session,
    public_session_summary,
    resolve_shared_session,
    revoke_workspace_share_session,
    revoke_share_session,
    share_server_status_payload,
    workspace_share_payload,
)


def verify_local_share_session_access(session_payload: dict) -> None:
    local_url = str(session_payload.get("local_url") or "").strip()
    session_id = str(session_payload.get("session_id") or "").strip()
    viewer_token = str(session_payload.get("viewer_token") or "").strip()
    if not local_url or not session_id or not viewer_token:
        raise RuntimeError("Local share validation requires a session_id, viewer_token, and local_url.")

    parsed = urlsplit(local_url)
    if not parsed.scheme or not parsed.netloc:
        raise RuntimeError(f"Local share URL is invalid: {local_url}")
    base_path = parsed.path
    if base_path.endswith("/share/view"):
        status_path = f"{base_path[:-len('/view')]}/api/status"
    elif base_path.endswith("/view"):
        status_path = f"{base_path[:-len('/view')]}/api/status"
    else:
        status_path = "/share/api/status"
    status_url = urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            status_path,
            urlencode({"session": session_id, "token": viewer_token}),
            "",
        )
    )
    deadline = time.monotonic() + 3.0
    while True:
        try:
            with urlopen(status_url, timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if int(getattr(response, "status", 200) or 200) != 200:
                    raise RuntimeError(f"Local share server responded with {getattr(response, 'status', '?')}.")
                if not isinstance(payload, dict):
                    raise RuntimeError("Local share server returned an unexpected payload.")
                return
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Local share server rejected the session ({exc.code}): {detail or exc.reason}") from exc
        except URLError as exc:
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Local share server is unreachable: {exc.reason}") from exc
            time.sleep(0.2)


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
        def prepare_share_server(previous_share_status: dict[str, object]) -> dict:
            share_status = start_share_server_process(
                ctx.workspace_root,
                host=bind_host,
                port=preferred_port,
                public_base_url=public_base_url,
            )
            share_server_for_response = dict(share_status)
            effective_bind_host = str(share_status.get("config", {}).get("bind_host", bind_host or "")).strip() or bind_host or ""
            should_start_quick_tunnel = (
                effective_bind_host == "0.0.0.0"
                and not public_base_url
                and bool(share_status.get("base_url"))
            )
            quick_tunnel_warning = ""
            if should_start_quick_tunnel:
                try:
                    tunnel_status = start_public_tunnel(ctx.workspace_root, str(share_status["base_url"]))
                    share_server_for_response["public_tunnel"] = tunnel_status
                    public_url = str(tunnel_status.get("public_url") or "").strip()
                    if public_url:
                        share_server_for_response["share_base_url"] = public_url
                        share_server_for_response["share_base_url_source"] = "quick_tunnel"
                except Exception as exc:
                    quick_tunnel_warning = str(exc).strip()
                    if project is not None:
                        append_ui_event(
                            project,
                            "share-tunnel-warning",
                            "Automatic public tunnel startup failed; the share session was not created because no public URL is available.",
                            {"error": quick_tunnel_warning},
                        )
            elif public_base_url or effective_bind_host != "0.0.0.0":
                share_server_for_response["public_tunnel"] = stop_public_tunnel(ctx.workspace_root)
            effective_share_base_url = str(share_server_for_response.get("share_base_url") or "").strip()
            effective_share_source = str(share_server_for_response.get("share_base_url_source") or "").strip().lower()
            if not effective_share_base_url or effective_share_source == "local":
                stop_public_tunnel(ctx.workspace_root)
                if not bool(previous_share_status.get("running")):
                    stop_share_server_process(ctx.workspace_root)
                if quick_tunnel_warning:
                    raise RuntimeError(f"Public share URL could not be created. {quick_tunnel_warning}")
                raise RuntimeError(
                    "Public share URL could not be created. Configure a public base URL or install cloudflared for automatic Quick Tunnel sharing."
                )
            return share_server_for_response

        def build_share_result(share_server_for_response: dict, session) -> dict:
            share = workspace_share_payload(ctx.workspace_root, context=project)
            share["server"] = {
                **share.get("server", {}),
                **share_server_for_response,
            }
            result = {
                "share": share,
                "created_share_session": public_session_summary(
                    ctx.workspace_root,
                    project,
                    session,
                    include_token=True,
                    server=share["server"],
                ),
            }
            if project is not None:
                result["project"] = {
                    "repo_id": project.metadata.repo_id,
                    "display_name": project.metadata.display_name or project.metadata.slug,
                    "project_dir": str(project.metadata.repo_path),
                }
            return result

        project = None
        if str(ctx.payload.get("repo_id", "")).strip() or str(ctx.payload.get("project_dir", "")).strip():
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
        previous_share_status = share_server_status_payload(ctx.workspace_root)
        share_server_for_response = prepare_share_server(previous_share_status)
        session = create_workspace_share_session(
            ctx.workspace_root,
            project,
            expires_in_minutes=expires_in_minutes,
            created_by=str(ctx.payload.get("created_by", "desktop-ui")).strip() or "desktop-ui",
        )
        if project is not None:
            append_ui_event(
                project,
                "share-session-created",
                "Created a temporary remote monitor share session.",
                {"session_id": session.session_id, "expires_at": session.expires_at},
            )
        result = build_share_result(share_server_for_response, session)
        try:
            verify_local_share_session_access(result["created_share_session"])
        except RuntimeError:
            stop_public_tunnel(ctx.workspace_root)
            stop_share_server_process(ctx.workspace_root)
            refreshed_previous = share_server_status_payload(ctx.workspace_root)
            share_server_for_response = prepare_share_server(refreshed_previous)
            result = build_share_result(share_server_for_response, session)
            verify_local_share_session_access(result["created_share_session"])
        return result

    def revoke_share(ctx: BridgeCommandContext) -> dict:
        current_project = None
        if str(ctx.payload.get("repo_id", "")).strip() or str(ctx.payload.get("project_dir", "")).strip():
            current_project = resolve_project(ctx.orchestrator, ctx.payload)
        session_id = str(ctx.payload.get("session_id", "")).strip()
        if not session_id:
            raise ValueError("session_id is required.")
        owner_project, _session = resolve_shared_session(ctx.workspace_root, session_id)
        session = (
            revoke_workspace_share_session(ctx.workspace_root, session_id)
            if owner_project is None
            else revoke_share_session(owner_project, session_id)
        )
        event_project = current_project or owner_project
        if event_project is not None:
            append_ui_event(
                event_project,
                "share-session-revoked",
                "Revoked a temporary remote monitor share session.",
                {"session_id": session.session_id},
            )
        share = workspace_share_payload(ctx.workspace_root, context=current_project)
        result = {
            "share": share,
            "revoked_share_session": public_session_summary(
                ctx.workspace_root,
                owner_project,
                session,
                include_token=False,
                server=share["server"],
            ),
        }
        if current_project is not None:
            result["project"] = {
                "repo_id": current_project.metadata.repo_id,
                "display_name": current_project.metadata.display_name or current_project.metadata.slug,
                "project_dir": str(current_project.metadata.repo_path),
            }
        return result

    return {
        "save_share_server_config": save_share_config,
        "start_share_server": start_share_server,
        "stop_share_server": lambda ctx: stop_share_server_process(ctx.workspace_root),
        "start_public_tunnel": start_public_share_tunnel,
        "stop_public_tunnel": lambda ctx: stop_public_tunnel(ctx.workspace_root),
        "create_share_session": create_share,
        "revoke_share_session": revoke_share,
    }

