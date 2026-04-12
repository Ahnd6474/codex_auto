from __future__ import annotations

from dataclasses import dataclass
import re

from .models import ExecutionStep, RuntimeOptions

DEFAULT_VERIFICATION_PROFILE = "default"
VERIFICATION_PROFILE_TAXONOMY = (
    DEFAULT_VERIFICATION_PROFILE,
    "contracts",
    "adapter",
    "integration",
    "schema",
    "migration",
)
_PROFILE_ALIASES = {
    "contract": "contracts",
    "contracts": "contracts",
    "shared_contracts": "contracts",
    "shared_contract": "contracts",
    "adapter": "adapter",
    "adapters": "adapter",
    "bridge": "adapter",
    "gateway": "adapter",
    "integration": "integration",
    "integrations": "integration",
    "merge": "integration",
    "schema": "schema",
    "schemas": "schema",
    "types": "schema",
    "migration": "migration",
    "migrations": "migration",
    "database_migration": "migration",
    "db_migration": "migration",
    "default": DEFAULT_VERIFICATION_PROFILE,
}
_ADAPTER_TOKENS = ("adapter", "bridge", "gateway", "shim", "wrapper", "client")
_CONTRACT_TOKENS = ("contract", "contracts", "api", "openapi", "graphql", "proto", "protobuf")
_INTEGRATION_TOKENS = ("integration", "integrate", "merge", "reconcile", "joined", "join", "cherry-pick")
_MIGRATION_TOKENS = ("migration", "migrate", "migrations", "alembic", "ddl", "schema.sql")
_SCHEMA_TOKENS = ("schema", "schemas", "interface", "interfaces", "type", "types", "dto")


@dataclass(slots=True)
class VerificationProfileSelection:
    profile: str
    source: str
    reason: str


@dataclass(slots=True)
class VerificationCommandResolution:
    profile: str
    profile_source: str
    profile_reason: str
    command: str
    command_source: str


def normalize_verification_profile(value: object, *, fallback: str = "") -> str:
    normalized = re.sub(r"[\s\-]+", "_", str(value or "").strip().lower()).strip("_")
    if not normalized:
        return fallback
    return _PROFILE_ALIASES.get(normalized, normalized)


def normalize_verification_profiles_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, str] = {}
    for raw_key, raw_command in value.items():
        key = normalize_verification_profile(raw_key)
        command = str(raw_command or "").strip()
        if not key or not command:
            continue
        normalized[key] = command
    return normalized


def verification_profile_taxonomy_text() -> str:
    return ", ".join(f"`{item}`" for item in VERIFICATION_PROFILE_TAXONOMY)


def select_verification_profile(step: ExecutionStep, *, step_kind: str | None = None) -> VerificationProfileSelection:
    metadata = step.metadata if isinstance(step.metadata, dict) else {}
    explicit = normalize_verification_profile(step.verification_profile or metadata.get("verification_profile", ""))
    if explicit:
        return VerificationProfileSelection(profile=explicit, source="explicit", reason="step field or metadata")

    normalized_step_kind = str(step_kind or metadata.get("step_kind", "")).strip().lower()
    if normalized_step_kind in {"join", "barrier"}:
        return VerificationProfileSelection(profile="integration", source="inferred", reason=f"step_kind:{normalized_step_kind}")

    normalized_step_type = str(step.step_type or metadata.get("step_type", "")).strip().lower()
    if normalized_step_type == "contract":
        return VerificationProfileSelection(profile="contracts", source="inferred", reason="step_type:contract")
    if normalized_step_type == "integration":
        return VerificationProfileSelection(profile="integration", source="inferred", reason="step_type:integration")

    shared_contracts = [str(item).strip() for item in (step.shared_contracts or metadata.get("shared_contracts", [])) if str(item).strip()]
    if bool(metadata.get("is_skeleton_contract")) or shared_contracts:
        return VerificationProfileSelection(profile="contracts", source="inferred", reason="shared_contracts_present")

    search_text = _search_text(step)
    search_paths = _search_paths(step)
    if _contains_any(search_paths, _MIGRATION_TOKENS) or _contains_any(search_text, _MIGRATION_TOKENS):
        return VerificationProfileSelection(profile="migration", source="inferred", reason="migration signal")
    if _contains_any(search_paths, _CONTRACT_TOKENS) or _contains_any(search_text, _CONTRACT_TOKENS):
        return VerificationProfileSelection(profile="contracts", source="inferred", reason="contract signal")
    if _contains_any(search_paths, _SCHEMA_TOKENS) or _contains_any(search_text, _SCHEMA_TOKENS):
        return VerificationProfileSelection(profile="schema", source="inferred", reason="schema signal")
    if _contains_any(search_paths, _ADAPTER_TOKENS) or _contains_any(search_text, _ADAPTER_TOKENS):
        return VerificationProfileSelection(profile="adapter", source="inferred", reason="adapter signal")
    if _contains_any(search_paths, _INTEGRATION_TOKENS) or _contains_any(search_text, _INTEGRATION_TOKENS):
        return VerificationProfileSelection(profile="integration", source="inferred", reason="integration signal")

    return VerificationProfileSelection(profile=DEFAULT_VERIFICATION_PROFILE, source="fallback_default", reason="no strong signal")


def resolve_verification_command(
    step: ExecutionStep | None,
    runtime: RuntimeOptions,
) -> VerificationCommandResolution:
    if step is None:
        selection = VerificationProfileSelection(
            profile=DEFAULT_VERIFICATION_PROFILE,
            source="fallback_default",
            reason="no execution step",
        )
        explicit_command = ""
    else:
        selection = select_verification_profile(step)
        explicit_command = str(step.test_command or "").strip()

    if explicit_command:
        return VerificationCommandResolution(
            profile=selection.profile,
            profile_source=selection.source,
            profile_reason=selection.reason,
            command=explicit_command,
            command_source="step_test_command",
        )

    profile_map = normalize_verification_profiles_map(getattr(runtime, "verification_profiles", {}))
    mapped_command = profile_map.get(selection.profile, "")
    if mapped_command:
        return VerificationCommandResolution(
            profile=selection.profile,
            profile_source=selection.source,
            profile_reason=selection.reason,
            command=mapped_command,
            command_source="verification_profile_map",
        )

    default_command = str(getattr(runtime, "test_cmd", "") or "").strip() or "python -m pytest"
    return VerificationCommandResolution(
        profile=selection.profile,
        profile_source=selection.source,
        profile_reason=selection.reason,
        command=default_command,
        command_source="runtime_test_cmd",
    )


def _contains_any(source: str, tokens: tuple[str, ...]) -> bool:
    normalized_source = source.lower()
    return any(token in normalized_source for token in tokens)


def _search_paths(step: ExecutionStep) -> str:
    metadata = step.metadata if isinstance(step.metadata, dict) else {}
    path_groups = [
        step.owned_paths,
        step.primary_scope_paths,
        step.shared_reviewed_paths,
        step.forbidden_core_paths,
        metadata.get("candidate_owned_paths", []),
    ]
    normalized_paths: list[str] = []
    for group in path_groups:
        if isinstance(group, list):
            normalized_paths.extend(str(item).strip().lower() for item in group if str(item).strip())
        elif isinstance(group, str) and group.strip():
            normalized_paths.append(group.strip().lower())
    return "\n".join(normalized_paths)


def _search_text(step: ExecutionStep) -> str:
    metadata = step.metadata if isinstance(step.metadata, dict) else {}
    text_parts = [
        step.title,
        step.display_description,
        step.codex_description,
        step.success_criteria,
        step.notes,
        metadata.get("implementation_notes", ""),
        metadata.get("join_reason", ""),
    ]
    return "\n".join(str(item).strip().lower() for item in text_parts if str(item).strip())
