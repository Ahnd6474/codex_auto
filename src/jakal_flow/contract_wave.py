from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any

from .models import ExecutionStep, ProjectPaths
from .utils import ensure_dir, now_utc_iso, read_json, write_json, write_text

STEP_TYPES = {"contract", "feature", "integration", "debug", "closeout"}
SCOPE_CLASSES = {"hard_owned", "shared_reviewed", "free_owned"}
PROMOTION_CLASSES = {"green", "yellow", "red"}
DEFAULT_SPINE_VERSION = "spine-v1"
DEFAULT_VERIFICATION_PROFILE = "default"


def _normalize(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return {key: _normalize(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def _normalize_choice(value: object, allowed: set[str], fallback: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in allowed:
        return normalized
    return fallback


def _normalize_path(value: object) -> str:
    normalized = str(value or "").strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.rstrip("/")


def _normalize_paths(values: object) -> list[str]:
    items: list[str]
    if isinstance(values, list):
        items = [str(item).strip() for item in values]
    elif isinstance(values, str):
        items = [part.strip() for part in values.replace("\r", "\n").replace(",", "\n").split("\n")]
    else:
        return []
    ordered: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = _normalize_path(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _normalize_strings(values: object) -> list[str]:
    items: list[str]
    if isinstance(values, list):
        items = [str(item).strip() for item in values]
    elif isinstance(values, str):
        items = [part.strip() for part in values.replace("\r", "\n").replace(",", "\n").split("\n")]
    else:
        return []
    ordered: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _step_kind(step: ExecutionStep) -> str:
    metadata = step.metadata if isinstance(step.metadata, dict) else {}
    normalized = str(metadata.get("step_kind", "")).strip().lower()
    if normalized in {"join", "barrier"}:
        return normalized
    return "task"


def _looks_like_closeout(step: ExecutionStep) -> bool:
    combined = " ".join(
        [
            step.title.strip().lower(),
            step.display_description.strip().lower(),
            step.codex_description.strip().lower(),
        ]
    )
    return "closeout" in combined or "final report" in combined


def _path_matches(candidate: str, scope_path: str) -> bool:
    normalized_candidate = _normalize_path(candidate)
    normalized_scope = _normalize_path(scope_path)
    if not normalized_candidate or not normalized_scope:
        return False
    return (
        normalized_candidate == normalized_scope
        or normalized_candidate.startswith(f"{normalized_scope}/")
        or normalized_scope.startswith(f"{normalized_candidate}/")
    )


def _paths_matching(paths: list[str], scope_paths: list[str]) -> list[str]:
    return [path for path in paths if any(_path_matches(path, scope_path) for scope_path in scope_paths)]


def _paths_excluding(paths: list[str], *excluded_scopes: list[str]) -> list[str]:
    excluded = [path for scope in excluded_scopes for path in scope]
    matched: list[str] = []
    for path in paths:
        if any(_path_matches(path, scope_path) for scope_path in excluded):
            continue
        matched.append(path)
    return matched


def default_step_type(step: ExecutionStep, *, step_kind: str | None = None) -> str:
    metadata = step.metadata if isinstance(step.metadata, dict) else {}
    explicit = _normalize_choice(step.step_type or metadata.get("step_type", ""), STEP_TYPES, "")
    if explicit:
        return explicit
    normalized_step_kind = str(step_kind or _step_kind(step)).strip().lower() or "task"
    if normalized_step_kind == "join":
        return "integration"
    if normalized_step_kind == "barrier":
        return "contract"
    if bool(metadata.get("is_skeleton_contract")) or _normalize_strings(step.shared_contracts or metadata.get("shared_contracts", [])):
        return "contract"
    if _looks_like_closeout(step):
        return "closeout"
    return "feature"


def declared_promotion_class(step: ExecutionStep, *, step_kind: str | None = None) -> str:
    normalized_step_kind = str(step_kind or _step_kind(step)).strip().lower() or "task"
    if normalized_step_kind in {"join", "barrier"}:
        return "red"
    if _normalize_choice(step.scope_class, SCOPE_CLASSES, "") == "hard_owned" or _normalize_paths(step.forbidden_core_paths):
        return "red"
    if default_step_type(step, step_kind=normalized_step_kind) == "integration":
        return "red"
    if (
        _normalize_choice(step.scope_class, SCOPE_CLASSES, "") == "shared_reviewed"
        or _normalize_paths(step.shared_reviewed_paths)
        or default_step_type(step, step_kind=normalized_step_kind) in {"contract", "debug", "closeout"}
    ):
        return "yellow"
    return "green"


def normalize_execution_step_policy(
    step: ExecutionStep,
    *,
    step_kind: str | None = None,
    current_spine_version: str = DEFAULT_SPINE_VERSION,
) -> ExecutionStep:
    metadata = dict(step.metadata) if isinstance(step.metadata, dict) else {}
    normalized_step_kind = str(step_kind or _step_kind(step)).strip().lower() or "task"
    step.step_type = default_step_type(step, step_kind=normalized_step_kind)
    step.shared_contracts = _normalize_strings(step.shared_contracts or metadata.get("shared_contracts", []))

    if step.shared_reviewed_paths or metadata.get("shared_reviewed_paths"):
        default_scope = "shared_reviewed"
    elif step.forbidden_core_paths or metadata.get("forbidden_core_paths"):
        default_scope = "hard_owned"
    else:
        default_scope = "free_owned"
    step.scope_class = _normalize_choice(step.scope_class or metadata.get("scope_class", ""), SCOPE_CLASSES, default_scope)
    step.spine_version = str(step.spine_version or metadata.get("spine_version", "")).strip() or current_spine_version
    step.verification_profile = str(step.verification_profile or metadata.get("verification_profile", "")).strip().lower() or DEFAULT_VERIFICATION_PROFILE
    step.primary_scope_paths = _normalize_paths(step.primary_scope_paths or metadata.get("primary_scope_paths", []) or step.owned_paths)
    step.shared_reviewed_paths = _normalize_paths(step.shared_reviewed_paths or metadata.get("shared_reviewed_paths", []))
    step.forbidden_core_paths = _normalize_paths(step.forbidden_core_paths or metadata.get("forbidden_core_paths", []))
    step.owned_paths = _normalize_paths(step.owned_paths or step.primary_scope_paths or metadata.get("owned_paths", []))
    if not step.primary_scope_paths:
        step.primary_scope_paths = list(step.owned_paths)
    step.promotion_class = declared_promotion_class(step, step_kind=normalized_step_kind)

    metadata["step_type"] = step.step_type
    metadata["scope_class"] = step.scope_class
    metadata["spine_version"] = step.spine_version
    metadata["shared_contracts"] = list(step.shared_contracts)
    metadata["verification_profile"] = step.verification_profile
    metadata["promotion_class"] = step.promotion_class
    metadata["primary_scope_paths"] = list(step.primary_scope_paths)
    metadata["shared_reviewed_paths"] = list(step.shared_reviewed_paths)
    metadata["forbidden_core_paths"] = list(step.forbidden_core_paths)
    step.metadata = metadata
    return step


def policy_summary(step: ExecutionStep) -> str:
    primary = ", ".join(step.primary_scope_paths) if step.primary_scope_paths else "none declared"
    shared = ", ".join(step.shared_reviewed_paths) if step.shared_reviewed_paths else "none"
    forbidden = ", ".join(step.forbidden_core_paths) if step.forbidden_core_paths else "none"
    contracts = ", ".join(step.shared_contracts) if step.shared_contracts else "none"
    return (
        f"step_type={step.step_type or 'feature'}; "
        f"scope_class={step.scope_class or 'free_owned'}; "
        f"spine_version={step.spine_version or DEFAULT_SPINE_VERSION}; "
        f"shared_contracts={contracts}; "
        f"primary_scope={primary}; "
        f"shared_reviewed={shared}; "
        f"forbidden_core={forbidden}; "
        f"verification_profile={step.verification_profile or DEFAULT_VERIFICATION_PROFILE}; "
        f"declared_promotion={step.promotion_class or 'green'}"
    )


@dataclass(slots=True)
class PromotionAssessment:
    promotion_class: str
    reason: str
    verification_passed: bool
    touched_files: list[str] = field(default_factory=list)
    touched_primary_paths: list[str] = field(default_factory=list)
    touched_shared_reviewed_paths: list[str] = field(default_factory=list)
    touched_forbidden_core_paths: list[str] = field(default_factory=list)
    outside_primary_paths: list[str] = field(default_factory=list)
    auto_promote_eligible: bool = False
    crr_required: bool = False
    explicit_policy_violation: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PromotionAssessment":
        return cls(
            promotion_class=_normalize_choice(data.get("promotion_class", ""), PROMOTION_CLASSES, "red"),
            reason=str(data.get("reason", "")).strip() or "unknown",
            verification_passed=bool(data.get("verification_passed", False)),
            touched_files=_normalize_paths(data.get("touched_files", [])),
            touched_primary_paths=_normalize_paths(data.get("touched_primary_paths", [])),
            touched_shared_reviewed_paths=_normalize_paths(data.get("touched_shared_reviewed_paths", [])),
            touched_forbidden_core_paths=_normalize_paths(data.get("touched_forbidden_core_paths", [])),
            outside_primary_paths=_normalize_paths(data.get("outside_primary_paths", [])),
            auto_promote_eligible=bool(data.get("auto_promote_eligible", False)),
            crr_required=bool(data.get("crr_required", False)),
            explicit_policy_violation=bool(data.get("explicit_policy_violation", False)),
        )


@dataclass(slots=True)
class SpineCheckpoint:
    version: str
    created_at: str
    step_id: str = ""
    lineage_id: str = ""
    commit_hash: str = ""
    shared_contracts: list[str] = field(default_factory=list)
    touched_files: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SpineCheckpoint":
        return cls(
            version=str(data.get("version", "")).strip() or DEFAULT_SPINE_VERSION,
            created_at=str(data.get("created_at", "")).strip() or now_utc_iso(),
            step_id=str(data.get("step_id", "")).strip(),
            lineage_id=str(data.get("lineage_id", "")).strip(),
            commit_hash=str(data.get("commit_hash", "")).strip(),
            shared_contracts=_normalize_strings(data.get("shared_contracts", [])),
            touched_files=_normalize_paths(data.get("touched_files", [])),
            notes=str(data.get("notes", "")).strip(),
        )


@dataclass(slots=True)
class SpineState:
    current_version: str = DEFAULT_SPINE_VERSION
    updated_at: str = ""
    history: list[SpineCheckpoint] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SpineState":
        history = data.get("history", [])
        return cls(
            current_version=str(data.get("current_version", "")).strip() or DEFAULT_SPINE_VERSION,
            updated_at=str(data.get("updated_at", "")).strip() or now_utc_iso(),
            history=[SpineCheckpoint.from_dict(item) for item in history if isinstance(item, dict)],
        )


@dataclass(slots=True)
class CommonRequirementRecord:
    request_id: str
    status: str = "open"
    created_at: str = ""
    resolved_at: str | None = None
    title: str = ""
    reason: str = ""
    promotion_class: str = "yellow"
    step_id: str = ""
    lineage_id: str = ""
    spine_version: str = DEFAULT_SPINE_VERSION
    affected_paths: list[str] = field(default_factory=list)
    shared_contracts: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CommonRequirementRecord":
        return cls(
            request_id=str(data.get("request_id", "")).strip(),
            status=str(data.get("status", "open")).strip().lower() or "open",
            created_at=str(data.get("created_at", "")).strip() or now_utc_iso(),
            resolved_at=(str(data.get("resolved_at", "")).strip() or None) if data.get("resolved_at") else None,
            title=str(data.get("title", "")).strip(),
            reason=str(data.get("reason", "")).strip(),
            promotion_class=_normalize_choice(data.get("promotion_class", ""), PROMOTION_CLASSES, "yellow"),
            step_id=str(data.get("step_id", "")).strip(),
            lineage_id=str(data.get("lineage_id", "")).strip(),
            spine_version=str(data.get("spine_version", "")).strip() or DEFAULT_SPINE_VERSION,
            affected_paths=_normalize_paths(data.get("affected_paths", [])),
            shared_contracts=_normalize_strings(data.get("shared_contracts", [])),
            notes=str(data.get("notes", "")).strip(),
        )


@dataclass(slots=True)
class CommonRequirementsState:
    updated_at: str = ""
    open_requirements: list[CommonRequirementRecord] = field(default_factory=list)
    resolved_requirements: list[CommonRequirementRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CommonRequirementsState":
        open_requirements = data.get("open_requirements", data.get("open", []))
        resolved_requirements = data.get("resolved_requirements", data.get("resolved", []))
        return cls(
            updated_at=str(data.get("updated_at", "")).strip() or now_utc_iso(),
            open_requirements=[CommonRequirementRecord.from_dict(item) for item in open_requirements if isinstance(item, dict)],
            resolved_requirements=[CommonRequirementRecord.from_dict(item) for item in resolved_requirements if isinstance(item, dict)],
        )


@dataclass(slots=True)
class LineageManifest:
    manifest_id: str
    lineage_id: str
    step_id: str
    step_title: str
    created_at: str
    step_type: str = "feature"
    scope_class: str = "free_owned"
    spine_version: str = DEFAULT_SPINE_VERSION
    touched_files: list[str] = field(default_factory=list)
    new_helpers_added: list[str] = field(default_factory=list)
    helpers_deleted: list[str] = field(default_factory=list)
    public_symbol_changes: list[str] = field(default_factory=list)
    config_changes: list[str] = field(default_factory=list)
    migration_changes: list[str] = field(default_factory=list)
    verification_commands: list[str] = field(default_factory=list)
    verification_summary: str = ""
    verification_status: str = "passed"
    shared_contracts_used: list[str] = field(default_factory=list)
    shared_contracts_changed: list[str] = field(default_factory=list)
    promotion_class: str = "green"
    promotion_reason: str = ""
    assessment: dict[str, Any] = field(default_factory=dict)
    commit_hash: str = ""
    common_requirement_request_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LineageManifest":
        return cls(
            manifest_id=str(data.get("manifest_id", "")).strip(),
            lineage_id=str(data.get("lineage_id", "")).strip(),
            step_id=str(data.get("step_id", "")).strip(),
            step_title=str(data.get("step_title", "")).strip(),
            created_at=str(data.get("created_at", "")).strip() or now_utc_iso(),
            step_type=_normalize_choice(data.get("step_type", ""), STEP_TYPES, "feature"),
            scope_class=_normalize_choice(data.get("scope_class", ""), SCOPE_CLASSES, "free_owned"),
            spine_version=str(data.get("spine_version", "")).strip() or DEFAULT_SPINE_VERSION,
            touched_files=_normalize_paths(data.get("touched_files", [])),
            new_helpers_added=_normalize_paths(data.get("new_helpers_added", [])),
            helpers_deleted=_normalize_paths(data.get("helpers_deleted", [])),
            public_symbol_changes=_normalize_paths(data.get("public_symbol_changes", [])),
            config_changes=_normalize_paths(data.get("config_changes", [])),
            migration_changes=_normalize_paths(data.get("migration_changes", [])),
            verification_commands=_normalize_strings(data.get("verification_commands", [])),
            verification_summary=str(data.get("verification_summary", "")).strip(),
            verification_status=str(data.get("verification_status", "passed")).strip().lower() or "passed",
            shared_contracts_used=_normalize_strings(data.get("shared_contracts_used", [])),
            shared_contracts_changed=_normalize_strings(data.get("shared_contracts_changed", [])),
            promotion_class=_normalize_choice(data.get("promotion_class", ""), PROMOTION_CLASSES, "green"),
            promotion_reason=str(data.get("promotion_reason", "")).strip(),
            assessment=data.get("assessment", {}) if isinstance(data.get("assessment", {}), dict) else {},
            commit_hash=str(data.get("commit_hash", "")).strip(),
            common_requirement_request_id=str(data.get("common_requirement_request_id", "")).strip(),
        )


def default_spine_state() -> SpineState:
    return SpineState(current_version=DEFAULT_SPINE_VERSION, updated_at=now_utc_iso(), history=[])


def default_common_requirements_state() -> CommonRequirementsState:
    return CommonRequirementsState(updated_at=now_utc_iso(), open_requirements=[], resolved_requirements=[])


def load_spine_state(path: Path) -> SpineState:
    raw = read_json(path, default={})
    if not isinstance(raw, dict):
        return default_spine_state()
    return SpineState.from_dict(raw)


def save_spine_state(path: Path, state: SpineState) -> SpineState:
    state.updated_at = state.updated_at or now_utc_iso()
    write_json(path, state.to_dict())
    return state


def load_common_requirements_state(path: Path) -> CommonRequirementsState:
    raw = read_json(path, default={})
    if not isinstance(raw, dict):
        return default_common_requirements_state()
    return CommonRequirementsState.from_dict(raw)


def save_common_requirements_state(path: Path, state: CommonRequirementsState) -> CommonRequirementsState:
    state.updated_at = state.updated_at or now_utc_iso()
    write_json(path, state.to_dict())
    return state


def _collect_shared_contract_names(spine_state: SpineState, requirements_state: CommonRequirementsState) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for checkpoint in spine_state.history:
        for name in checkpoint.shared_contracts:
            if name in seen:
                continue
            seen.add(name)
            ordered.append(name)
    for record in [*requirements_state.open_requirements, *requirements_state.resolved_requirements]:
        for name in record.shared_contracts:
            if name in seen:
                continue
            seen.add(name)
            ordered.append(name)
    return ordered


def render_shared_contracts_markdown(
    spine_state: SpineState,
    requirements_state: CommonRequirementsState,
) -> str:
    contract_names = _collect_shared_contract_names(spine_state, requirements_state)
    lines = [
        "# Shared Contracts",
        "",
        "Guarded-overlap contract-wave state for the current managed repository.",
        "",
        f"- Current spine version: {spine_state.current_version or DEFAULT_SPINE_VERSION}",
        f"- Last updated: {spine_state.updated_at or requirements_state.updated_at or now_utc_iso()}",
        f"- Known shared contracts: {', '.join(contract_names) if contract_names else 'none recorded'}",
        "",
        "## Spine History",
    ]
    if not spine_state.history:
        lines.extend(["- No contract checkpoints recorded yet.", ""])
    else:
        for checkpoint in spine_state.history:
            lines.extend(
                [
                    f"- {checkpoint.version} | step={checkpoint.step_id or 'n/a'} | lineage={checkpoint.lineage_id or 'n/a'} | contracts={', '.join(checkpoint.shared_contracts) or 'none'}",
                    f"  touched={', '.join(checkpoint.touched_files) or 'none'} | commit={checkpoint.commit_hash or 'n/a'}",
                ]
            )
        lines.append("")
    lines.extend(["## Open Common Requirements", ""])
    if not requirements_state.open_requirements:
        lines.extend(["- none", ""])
    else:
        for record in requirements_state.open_requirements:
            lines.append(
                f"- {record.request_id}: {record.title or record.reason or 'common requirement'} | promotion={record.promotion_class} | step={record.step_id or 'n/a'} | contracts={', '.join(record.shared_contracts) or 'none'} | paths={', '.join(record.affected_paths) or 'none'}"
            )
        lines.append("")
    lines.extend(["## Resolved Common Requirements", ""])
    if not requirements_state.resolved_requirements:
        lines.append("- none")
    else:
        for record in requirements_state.resolved_requirements:
            lines.append(
                f"- {record.request_id}: {record.title or record.reason or 'common requirement'} | resolved_at={record.resolved_at or 'n/a'} | step={record.step_id or 'n/a'}"
            )
    lines.append("")
    return "\n".join(lines)


def ensure_contract_wave_artifacts(paths: ProjectPaths) -> None:
    ensure_dir(paths.lineage_manifests_dir)
    if not paths.spine_file.exists():
        save_spine_state(paths.spine_file, default_spine_state())
    if not paths.common_requirements_file.exists():
        save_common_requirements_state(paths.common_requirements_file, default_common_requirements_state())
    if not paths.shared_contracts_file.exists():
        write_text(
            paths.shared_contracts_file,
            render_shared_contracts_markdown(default_spine_state(), default_common_requirements_state()),
        )


def current_spine_version(paths: ProjectPaths) -> str:
    ensure_contract_wave_artifacts(paths)
    return load_spine_state(paths.spine_file).current_version or DEFAULT_SPINE_VERSION


def _advance_spine_version(current_version: str) -> str:
    normalized = str(current_version or "").strip() or DEFAULT_SPINE_VERSION
    prefix, sep, suffix = normalized.rpartition("v")
    if sep and suffix.isdigit():
        return f"{prefix}v{int(suffix) + 1}"
    if normalized.endswith("-"):
        return f"{normalized}1"
    return f"{normalized}-1"


def classify_completed_lineage_step(
    step: ExecutionStep,
    *,
    changed_files: list[str],
    verification_passed: bool,
    batch_size: int,
    child_count: int,
    step_kind: str = "task",
    explicit_policy_violation: bool = False,
    unresolved_reservation: bool = False,
) -> PromotionAssessment:
    normalize_execution_step_policy(step, step_kind=step_kind)
    touched_files = _normalize_paths(changed_files)
    touched_primary = _paths_matching(touched_files, step.primary_scope_paths)
    touched_shared = _paths_matching(touched_files, step.shared_reviewed_paths)
    touched_forbidden = _paths_matching(touched_files, step.forbidden_core_paths)
    outside_primary = _paths_excluding(touched_files, step.primary_scope_paths, step.shared_reviewed_paths, step.forbidden_core_paths)

    promotion_class = "green"
    reason = "green_leaf_owned_scope"
    if not verification_passed:
        promotion_class = "red"
        reason = "verification_failed"
    elif step_kind != "task":
        promotion_class = "red"
        reason = "topology_step_requires_integration"
    elif explicit_policy_violation:
        promotion_class = "red"
        reason = "explicit_policy_violation"
    elif unresolved_reservation:
        promotion_class = "red"
        reason = "unresolved_reservation"
    elif step.step_type == "integration":
        promotion_class = "red"
        reason = "integration_step_requires_join_flow"
    elif step.scope_class == "hard_owned" or touched_forbidden:
        promotion_class = "red"
        reason = "touched_hard_owned_or_core_scope"
    elif (
        step.scope_class == "shared_reviewed"
        or touched_shared
        or outside_primary
        or step.step_type in {"contract", "debug", "closeout"}
    ):
        promotion_class = "yellow"
        if touched_shared:
            reason = "touched_shared_reviewed_scope"
        elif outside_primary:
            reason = "touched_outside_primary_scope"
        elif step.step_type == "contract":
            reason = "contract_wave_requires_integration_review"
        else:
            reason = f"{step.step_type}_step_requires_review"

    crr_required = promotion_class in {"yellow", "red"} and (
        bool(step.shared_contracts)
        or bool(touched_shared)
        or bool(touched_forbidden)
        or step.step_type == "contract"
    )
    auto_promote_eligible = (
        promotion_class == "green"
        and verification_passed
        and batch_size == 1
        and step_kind == "task"
        and child_count == 0
    )
    return PromotionAssessment(
        promotion_class=promotion_class,
        reason=reason,
        verification_passed=verification_passed,
        touched_files=touched_files,
        touched_primary_paths=touched_primary,
        touched_shared_reviewed_paths=touched_shared,
        touched_forbidden_core_paths=touched_forbidden,
        outside_primary_paths=outside_primary,
        auto_promote_eligible=auto_promote_eligible,
        crr_required=crr_required,
        explicit_policy_violation=explicit_policy_violation,
    )


def _is_helper_path(path: str) -> bool:
    normalized = _normalize_path(path).lower()
    leaf = normalized.rsplit("/", 1)[-1]
    return (
        "/helpers/" in normalized
        or leaf.endswith("_helper.py")
        or leaf.endswith("_helpers.py")
        or leaf == "helpers.py"
    )


def _is_public_api_path(path: str) -> bool:
    normalized = _normalize_path(path).lower()
    leaf = normalized.rsplit("/", 1)[-1]
    return (
        "/api/" in normalized
        or "/contracts/" in normalized
        or leaf == "__init__.py"
        or leaf.endswith("_api.py")
        or "schema" in leaf
        or leaf.endswith("types.py")
    )


def _is_config_path(path: str) -> bool:
    normalized = _normalize_path(path).lower()
    leaf = normalized.rsplit("/", 1)[-1]
    return (
        "/config/" in normalized
        or leaf.endswith((".json", ".toml", ".yaml", ".yml", ".ini", ".cfg"))
        or leaf in {".env", ".env.example"}
    )


def _is_migration_path(path: str) -> bool:
    normalized = _normalize_path(path).lower()
    return (
        "/migrations/" in normalized
        or "/migration/" in normalized
        or "alembic" in normalized
        or normalized.endswith(".sql")
    )


def build_lineage_manifest(
    *,
    lineage_id: str,
    step: ExecutionStep,
    changed_files: list[str],
    diff_entries: list[tuple[str, str]] | None,
    verification_command: str,
    verification_summary: str,
    verification_passed: bool,
    assessment: PromotionAssessment,
    commit_hash: str,
) -> LineageManifest:
    normalize_execution_step_policy(step)
    touched_files = _normalize_paths(changed_files)
    normalized_diffs = [
        (str(status or "").strip().upper(), _normalize_path(path))
        for status, path in (diff_entries or [])
        if _normalize_path(path)
    ]
    new_helpers = [path for status, path in normalized_diffs if status.startswith("A") and _is_helper_path(path)]
    deleted_helpers = [path for status, path in normalized_diffs if status.startswith("D") and _is_helper_path(path)]
    manifest_id = f"{lineage_id.lower()}-{step.step_id.lower()}-{''.join(char for char in now_utc_iso() if char.isdigit())[:14]}"
    shared_contracts_changed = list(step.shared_contracts) if step.step_type == "contract" or assessment.crr_required else []
    return LineageManifest(
        manifest_id=manifest_id,
        lineage_id=lineage_id,
        step_id=step.step_id,
        step_title=step.title,
        created_at=now_utc_iso(),
        step_type=step.step_type or "feature",
        scope_class=step.scope_class or "free_owned",
        spine_version=step.spine_version or DEFAULT_SPINE_VERSION,
        touched_files=touched_files,
        new_helpers_added=new_helpers,
        helpers_deleted=deleted_helpers,
        public_symbol_changes=[path for path in touched_files if _is_public_api_path(path)],
        config_changes=[path for path in touched_files if _is_config_path(path)],
        migration_changes=[path for path in touched_files if _is_migration_path(path)],
        verification_commands=_normalize_strings([verification_command]),
        verification_summary=verification_summary.strip(),
        verification_status="passed" if verification_passed else "failed",
        shared_contracts_used=list(step.shared_contracts),
        shared_contracts_changed=shared_contracts_changed,
        promotion_class=assessment.promotion_class,
        promotion_reason=assessment.reason,
        assessment=assessment.to_dict(),
        commit_hash=commit_hash.strip(),
    )


def _manifest_file(paths: ProjectPaths, manifest: LineageManifest) -> Path:
    timestamp = "".join(char for char in manifest.created_at if char.isdigit())[:14] or "00000000000000"
    return paths.lineage_manifests_dir / f"{timestamp}_{manifest.lineage_id.lower()}_{manifest.step_id.lower()}.json"


def save_lineage_manifest(paths: ProjectPaths, manifest: LineageManifest) -> Path:
    ensure_contract_wave_artifacts(paths)
    target = _manifest_file(paths, manifest)
    write_json(target, manifest.to_dict())
    return target


def load_lineage_manifests(paths: ProjectPaths, *, lineage_id: str = "") -> list[LineageManifest]:
    ensure_contract_wave_artifacts(paths)
    manifests: list[LineageManifest] = []
    target_lineage = str(lineage_id).strip()
    for item in sorted(paths.lineage_manifests_dir.glob("*.json")):
        raw = read_json(item, default={})
        if not isinstance(raw, dict):
            continue
        manifest = LineageManifest.from_dict(raw)
        if target_lineage and manifest.lineage_id != target_lineage:
            continue
        manifests.append(manifest)
    return manifests


def load_lineage_manifest_payloads(paths: ProjectPaths) -> list[dict[str, Any]]:
    return [manifest.to_dict() for manifest in load_lineage_manifests(paths)]


def manifest_summary_markdown(manifests: list[LineageManifest]) -> str:
    lines = [
        "# Lineage Manifest Summary",
        "",
        "Completed lineage work captured for integration, merger, and review passes.",
        "",
    ]
    if not manifests:
        lines.append("- No lineage manifests recorded yet.")
        lines.append("")
        return "\n".join(lines)
    for manifest in manifests:
        lines.extend(
            [
                f"## {manifest.lineage_id} / {manifest.step_id}",
                f"- Step: {manifest.step_title}",
                f"- Step type: {manifest.step_type}",
                f"- Scope class: {manifest.scope_class}",
                f"- Spine version: {manifest.spine_version}",
                f"- Promotion: {manifest.promotion_class} ({manifest.promotion_reason or 'n/a'})",
                f"- Touched files: {', '.join(manifest.touched_files) if manifest.touched_files else 'none'}",
                f"- Shared contracts used: {', '.join(manifest.shared_contracts_used) if manifest.shared_contracts_used else 'none'}",
                f"- Shared contracts changed: {', '.join(manifest.shared_contracts_changed) if manifest.shared_contracts_changed else 'none'}",
                f"- Verification: {', '.join(manifest.verification_commands) if manifest.verification_commands else 'none'}",
                f"- Verification status: {manifest.verification_status}",
                f"- Config changes: {', '.join(manifest.config_changes) if manifest.config_changes else 'none'}",
                f"- Migration changes: {', '.join(manifest.migration_changes) if manifest.migration_changes else 'none'}",
                "",
            ]
        )
    return "\n".join(lines)


def _next_common_requirement_id(state: CommonRequirementsState) -> str:
    next_index = 1
    for record in [*state.open_requirements, *state.resolved_requirements]:
        raw_id = str(record.request_id or "").strip().upper()
        if raw_id.startswith("CRR") and raw_id[3:].isdigit():
            next_index = max(next_index, int(raw_id[3:]) + 1)
    return f"CRR{next_index}"


def _matching_requirement(
    state: CommonRequirementsState,
    *,
    lineage_id: str,
    step_id: str,
    shared_contracts: list[str],
    affected_paths: list[str],
) -> CommonRequirementRecord | None:
    requested_contracts = set(shared_contracts)
    for record in state.open_requirements:
        if record.lineage_id == lineage_id and record.step_id == step_id:
            return record
        if requested_contracts and requested_contracts.intersection(record.shared_contracts):
            return record
        if affected_paths and any(_path_matches(path, scope_path) for path in affected_paths for scope_path in record.affected_paths):
            return record
    return None


def update_contract_wave_artifacts_for_completion(
    paths: ProjectPaths,
    *,
    step: ExecutionStep,
    lineage_id: str,
    manifest: LineageManifest,
    assessment: PromotionAssessment,
) -> tuple[SpineState, CommonRequirementsState, CommonRequirementRecord | None]:
    ensure_contract_wave_artifacts(paths)
    spine_state = load_spine_state(paths.spine_file)
    requirements_state = load_common_requirements_state(paths.common_requirements_file)
    timestamp = now_utc_iso()
    normalize_execution_step_policy(step, current_spine_version=spine_state.current_version)

    if step.step_type == "contract" and manifest.verification_status == "passed":
        next_version = str(step.spine_version).strip()
        if not next_version or next_version == spine_state.current_version:
            next_version = _advance_spine_version(spine_state.current_version)
        manifest.spine_version = next_version
        step.spine_version = next_version
        spine_state.current_version = next_version
        spine_state.history.append(
            SpineCheckpoint(
                version=next_version,
                created_at=timestamp,
                step_id=step.step_id,
                lineage_id=lineage_id,
                commit_hash=manifest.commit_hash,
                shared_contracts=list(step.shared_contracts),
                touched_files=list(manifest.touched_files),
                notes=manifest.promotion_reason,
            )
        )
    spine_state.updated_at = timestamp

    resolved_open: list[CommonRequirementRecord] = []
    remaining_open: list[CommonRequirementRecord] = []
    if step.step_type == "contract" and manifest.verification_status == "passed":
        for record in requirements_state.open_requirements:
            if (
                set(record.shared_contracts).intersection(step.shared_contracts)
                or any(_path_matches(path, scope_path) for path in manifest.touched_files for scope_path in record.affected_paths)
            ):
                record.status = "resolved"
                record.resolved_at = timestamp
                record.notes = (record.notes + f" | resolved by {step.step_id}").strip(" |")
                resolved_open.append(record)
            else:
                remaining_open.append(record)
        requirements_state.open_requirements = remaining_open
        requirements_state.resolved_requirements.extend(resolved_open)

    created_record: CommonRequirementRecord | None = None
    if assessment.crr_required:
        existing = _matching_requirement(
            requirements_state,
            lineage_id=lineage_id,
            step_id=step.step_id,
            shared_contracts=step.shared_contracts,
            affected_paths=assessment.touched_shared_reviewed_paths + assessment.touched_forbidden_core_paths + assessment.outside_primary_paths,
        )
        if existing is None:
            created_record = CommonRequirementRecord(
                request_id=_next_common_requirement_id(requirements_state),
                status="open",
                created_at=timestamp,
                title=f"{step.step_id} shared requirement review",
                reason=assessment.reason,
                promotion_class=assessment.promotion_class,
                step_id=step.step_id,
                lineage_id=lineage_id,
                spine_version=manifest.spine_version or spine_state.current_version,
                affected_paths=assessment.touched_shared_reviewed_paths + assessment.touched_forbidden_core_paths + assessment.outside_primary_paths,
                shared_contracts=list(step.shared_contracts),
                notes=f"Promotion routed to {assessment.promotion_class}.",
            )
            requirements_state.open_requirements.append(created_record)
        else:
            created_record = existing
    requirements_state.updated_at = timestamp

    if created_record is not None:
        manifest.common_requirement_request_id = created_record.request_id

    save_spine_state(paths.spine_file, spine_state)
    save_common_requirements_state(paths.common_requirements_file, requirements_state)
    write_text(paths.shared_contracts_file, render_shared_contracts_markdown(spine_state, requirements_state))
    return spine_state, requirements_state, created_record
