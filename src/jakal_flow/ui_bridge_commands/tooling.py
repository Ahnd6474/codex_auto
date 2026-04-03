from __future__ import annotations

from typing import Any

from ..model_providers import builtin_model_catalog, discover_local_model_catalog
from ..step_models import provider_statuses_payload
from ..tooling_manager import get_tooling_statuses, run_tooling_action
from .context import BridgeCommandContext, BridgeCommandHandler


def _merge_model_catalogs(*catalogs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for catalog in catalogs:
        for item in catalog:
            if not isinstance(item, dict):
                continue
            provider = str(item.get("provider", "openai")).strip().lower() or "openai"
            local_provider = str(item.get("local_provider", "")).strip().lower()
            model = str(item.get("model", "")).strip().lower()
            if not model:
                continue
            key = (provider, local_provider, model)
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def _fallback_tooling_snapshot(
    *,
    tooling_statuses: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    provider_statuses = provider_statuses_payload(force_refresh=False)
    model_catalog = _merge_model_catalogs(
        builtin_model_catalog(),
        discover_local_model_catalog(force_refresh=False),
    )
    codex_status = {
        "available": any(bool(item.get("available")) for item in provider_statuses.values()),
        "account": {
            "authenticated": False,
            "requires_openai_auth": True,
            "type": "",
            "email": "",
            "plan_type": "unknown",
        },
        "rate_limits": {
            "default_limit_id": "",
            "items": [],
        },
        "model_catalog": model_catalog,
        "provider_statuses": provider_statuses,
        "error": "",
    }
    return {
        "codex_status": codex_status,
        "model_catalog": model_catalog,
        "tooling_statuses": (
            tooling_statuses
            if tooling_statuses is not None
            else get_tooling_statuses(force_refresh=False, startup_safe=True)
        ),
    }


def tooling_snapshot_payload(
    *,
    codex_snapshot_service,
    force_refresh: bool = False,
    prefer_cached: bool = False,
    include_ollama_details: bool = False,
    refresh_codex_status: bool = True,
) -> dict[str, Any]:
    if prefer_cached and not force_refresh:
        cached_snapshot = codex_snapshot_service.peek_snapshot()
        if cached_snapshot is None:
            return _fallback_tooling_snapshot()
        codex_status = cached_snapshot.to_dict()
        codex_status["provider_statuses"] = provider_statuses_payload(force_refresh=False)
        return {
            "codex_status": codex_status,
            "model_catalog": codex_status.get("model_catalog", []),
            "tooling_statuses": get_tooling_statuses(force_refresh=False, startup_safe=True),
        }

    tooling_statuses = get_tooling_statuses(
        force_refresh=force_refresh,
        include_ollama_details=include_ollama_details,
    )
    if not refresh_codex_status:
        cached_snapshot = codex_snapshot_service.peek_snapshot()
        if cached_snapshot is None:
            return _fallback_tooling_snapshot(tooling_statuses=tooling_statuses)
        codex_status = cached_snapshot.to_dict()
        codex_status["provider_statuses"] = provider_statuses_payload(force_refresh=False)
        return {
            "codex_status": codex_status,
            "model_catalog": codex_status.get("model_catalog", []),
            "tooling_statuses": tooling_statuses,
        }

    fetch_snapshot = lambda codex_path="": codex_snapshot_service.get_snapshot(  # noqa: E731
        codex_path,
        force_refresh=force_refresh,
    )
    codex_status = fetch_snapshot().to_dict()
    codex_status["provider_statuses"] = provider_statuses_payload(
        fetch_snapshot=fetch_snapshot,
        force_refresh=force_refresh,
    )
    return {
        "codex_status": codex_status,
        "model_catalog": codex_status.get("model_catalog", []),
        "tooling_statuses": tooling_statuses,
    }


def build_tooling_command_handlers(
    *,
    coerce_bool,
    codex_snapshot_service,
) -> dict[str, BridgeCommandHandler]:
    def get_tooling_status(ctx: BridgeCommandContext) -> dict[str, Any]:
        force_refresh = coerce_bool(ctx.payload.get("force_refresh", False), False)
        include_ollama_details = coerce_bool(ctx.payload.get("include_ollama_details", False), False)
        refresh_codex_status = coerce_bool(ctx.payload.get("refresh_codex_status", True), True)
        return {
            **tooling_snapshot_payload(
                codex_snapshot_service=codex_snapshot_service,
                force_refresh=force_refresh,
                include_ollama_details=include_ollama_details,
                refresh_codex_status=refresh_codex_status,
            ),
            "emit_project_changed": False,
        }

    def manage_tooling(ctx: BridgeCommandContext) -> dict[str, Any]:
        action = str(ctx.payload.get("action", "")).strip().lower()
        tool = str(ctx.payload.get("tool", "")).strip().lower()
        model = str(ctx.payload.get("model", "")).strip().lower()
        action_result = run_tooling_action(
            ctx.workspace_root,
            action=action,
            tool=tool,
            model=model,
        )
        return {
            **tooling_snapshot_payload(
                codex_snapshot_service=codex_snapshot_service,
                force_refresh=True,
                include_ollama_details=(tool == "ollama" and action == "connect"),
            ),
            "tooling_action": action_result,
            "emit_project_changed": False,
        }

    return {
        "get-tooling-status": get_tooling_status,
        "manage-tooling": manage_tooling,
    }
