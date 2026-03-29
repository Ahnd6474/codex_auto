from __future__ import annotations

from ..contract_wave import record_manual_spine_checkpoint, set_common_requirement_status
from .context import BridgeCommandContext, BridgeCommandHandler


def build_contract_command_handlers(
    *,
    resolve_project,
    append_ui_event,
) -> dict[str, BridgeCommandHandler]:
    def resolve_common_requirement(ctx: BridgeCommandContext) -> dict:
        project = resolve_project(ctx.orchestrator, ctx.payload)
        request_id = str(ctx.payload.get("request_id", "")).strip()
        if not request_id:
            raise ValueError("request_id is required.")
        note = str(ctx.payload.get("note", "")).strip()
        _spine, _requirements, record = set_common_requirement_status(
            project.paths,
            request_id=request_id,
            status="resolved",
            note=note,
        )
        append_ui_event(
            project,
            "common-requirement-resolved",
            f"Resolved common requirement {record.request_id}.",
            {
                "request_id": record.request_id,
                "status": record.status,
                "resolved_at": record.resolved_at,
                "promotion_class": record.promotion_class,
                "note": note,
            },
        )
        return ctx.detail_payload(project, refresh_codex_status=False, detail_level="full")

    def reopen_common_requirement(ctx: BridgeCommandContext) -> dict:
        project = resolve_project(ctx.orchestrator, ctx.payload)
        request_id = str(ctx.payload.get("request_id", "")).strip()
        if not request_id:
            raise ValueError("request_id is required.")
        note = str(ctx.payload.get("note", "")).strip()
        _spine, _requirements, record = set_common_requirement_status(
            project.paths,
            request_id=request_id,
            status="open",
            note=note,
        )
        append_ui_event(
            project,
            "common-requirement-reopened",
            f"Reopened common requirement {record.request_id}.",
            {
                "request_id": record.request_id,
                "status": record.status,
                "promotion_class": record.promotion_class,
                "note": note,
            },
        )
        return ctx.detail_payload(project, refresh_codex_status=False, detail_level="full")

    def record_spine_checkpoint(ctx: BridgeCommandContext) -> dict:
        project = resolve_project(ctx.orchestrator, ctx.payload)
        version = str(ctx.payload.get("version", "")).strip()
        notes = str(ctx.payload.get("notes", "")).strip()
        shared_contracts = ctx.payload.get("shared_contracts", [])
        touched_files = ctx.payload.get("touched_files", [])
        step_id = str(ctx.payload.get("step_id", "")).strip()
        lineage_id = str(ctx.payload.get("lineage_id", "")).strip()
        commit_hash = str(ctx.payload.get("commit_hash", "")).strip()
        _spine, _requirements, checkpoint = record_manual_spine_checkpoint(
            project.paths,
            version=version,
            notes=notes,
            shared_contracts=shared_contracts,
            touched_files=touched_files,
            step_id=step_id,
            lineage_id=lineage_id,
            commit_hash=commit_hash,
        )
        append_ui_event(
            project,
            "spine-checkpoint-recorded",
            f"Recorded spine checkpoint {checkpoint.version}.",
            {
                "version": checkpoint.version,
                "step_id": checkpoint.step_id,
                "lineage_id": checkpoint.lineage_id,
                "shared_contracts": checkpoint.shared_contracts,
                "touched_files": checkpoint.touched_files,
                "notes": checkpoint.notes,
            },
        )
        return ctx.detail_payload(project, refresh_codex_status=False, detail_level="full")

    return {
        "resolve-common-requirement": resolve_common_requirement,
        "reopen-common-requirement": reopen_common_requirement,
        "record-spine-checkpoint": record_spine_checkpoint,
    }
