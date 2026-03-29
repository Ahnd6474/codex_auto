from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
import json

from .models import ExecutionPlanState, ExecutionStep, RuntimeOptions
from .step_models import resolve_step_model_choice
from .utils import parse_json_text, similarity_score


@dataclass(frozen=True)
class PlannerOutlineBlock:
    block_id: str
    title: str
    candidate_owned_paths: list[str]
    parallelizable_after: list[str]
    implementation_notes: str
    is_skeleton_contract: bool = False
    skeleton_contract_docstring: str = ""


def coerce_string_list(value: object) -> list[str]:
    items: list[str]
    if isinstance(value, list):
        items = [str(item).strip() for item in value]
    elif isinstance(value, str):
        items = [part.strip() for part in value.replace("\r", "\n").replace(",", "\n").split("\n")]
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


def normalize_owned_path(value: str) -> str:
    normalized = str(value).strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.rstrip("/")


def normalize_owned_paths(value: object) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for item in coerce_string_list(value):
        normalized = normalize_owned_path(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def parse_planner_outline_payload(planner_outline: str) -> dict[str, object]:
    raw = planner_outline.strip()
    if not raw:
        return {}
    try:
        payload = parse_json_text(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def planner_outline_blocks(outline: dict[str, object]) -> list[PlannerOutlineBlock]:
    blocks: list[PlannerOutlineBlock] = []

    skeleton_payload = outline.get("skeleton_step")
    if not isinstance(skeleton_payload, dict):
        skeleton_payload = outline.get("bootstrap_step")
    if isinstance(skeleton_payload, dict) and bool(skeleton_payload.get("needed")):
        blocks.append(
            PlannerOutlineBlock(
                block_id=str(skeleton_payload.get("block_id", "")).strip() or "SK1",
                title=str(skeleton_payload.get("task_title", "")).strip() or "Skeleton bootstrap",
                candidate_owned_paths=coerce_string_list(skeleton_payload.get("candidate_owned_paths", [])),
                parallelizable_after=[],
                implementation_notes="",
                is_skeleton_contract=True,
                skeleton_contract_docstring=str(
                    skeleton_payload.get("contract_docstring", skeleton_payload.get("executor_docstring", ""))
                ).strip(),
            )
        )

    candidate_payload = outline.get("candidate_blocks")
    if not isinstance(candidate_payload, list):
        candidate_payload = outline.get("candidate_experiments")
    if isinstance(candidate_payload, list):
        for index, item in enumerate(candidate_payload, start=1):
            if not isinstance(item, dict):
                continue
            blocks.append(
                PlannerOutlineBlock(
                    block_id=str(item.get("block_id", "")).strip() or f"B{index}",
                    title=str(item.get("goal", item.get("task_title", ""))).strip() or f"Candidate block {index}",
                    candidate_owned_paths=coerce_string_list(item.get("candidate_owned_paths", [])),
                    parallelizable_after=coerce_string_list(item.get("parallelizable_after", [])),
                    implementation_notes=str(
                        item.get("implementation_notes", item.get("executor_docstring", ""))
                    ).strip(),
                )
            )
    return blocks


def planner_outline_shared_contracts(outline: dict[str, object]) -> set[str]:
    names = coerce_string_list(outline.get("shared_contracts", []))
    names.extend(coerce_string_list(outline.get("guardrail_contracts", [])))
    return {item.strip().lower() for item in names if item.strip()}


def match_step_to_planner_outline_block(
    step: ExecutionStep,
    outline_blocks: list[PlannerOutlineBlock],
) -> PlannerOutlineBlock | None:
    metadata = step.metadata if isinstance(step.metadata, dict) else {}
    candidate_block_id = str(metadata.get("candidate_block_id", "")).strip()
    if candidate_block_id:
        for block in outline_blocks:
            if block.block_id == candidate_block_id:
                return block

    normalized_title = step.title.strip().lower()
    if normalized_title:
        for block in outline_blocks:
            block_title = block.title.strip().lower()
            if block_title and block_title == normalized_title:
                return block

    best_block: PlannerOutlineBlock | None = None
    best_score = 0.0
    for block in outline_blocks:
        if not block.title:
            continue
        score = similarity_score(step.title, block.title)
        if score > best_score:
            best_score = score
            best_block = block
    if best_score >= 0.45:
        return best_block
    return None


def apply_skeleton_contract_docstring(codex_description: str, contract_docstring: str) -> str:
    base = codex_description.strip()
    normalized_docstring = " ".join(contract_docstring.split())
    if not normalized_docstring:
        return base
    if normalized_docstring.lower() in base.lower():
        return base
    instruction = (
        f"If the relevant module, class, or function already exists, update it in place; otherwise create only the "
        f'smallest necessary skeleton with this contract docstring: """{normalized_docstring}"""'
    )
    return f"{base} {instruction}".strip()


def resolve_parallelizable_dependencies(
    values: list[str],
    *,
    step_by_block_id: dict[str, str],
    shared_contracts: set[str],
    skeleton_step_id: str,
    current_step_id: str,
) -> list[str]:
    resolved: list[str] = []
    seen: set[str] = set()
    for item in values:
        normalized = str(item).strip()
        if not normalized:
            continue
        target_step_id = step_by_block_id.get(normalized, "")
        if not target_step_id and skeleton_step_id and normalized.lower() in shared_contracts:
            target_step_id = skeleton_step_id
        if not target_step_id or target_step_id == current_step_id or target_step_id in seen:
            continue
        seen.add(target_step_id)
        resolved.append(target_step_id)
    return resolved


def repack_parallelizable_steps(
    steps: list[ExecutionStep],
    *,
    step_by_block_id: dict[str, str],
    shared_contracts: set[str],
) -> None:
    step_index = {step.step_id: index for index, step in enumerate(steps)}
    skeleton_step_id = ""
    for step in steps:
        metadata = step.metadata if isinstance(step.metadata, dict) else {}
        if metadata.get("is_skeleton_contract"):
            skeleton_step_id = step.step_id
            break

    for step in steps:
        metadata = step.metadata if isinstance(step.metadata, dict) else {}
        parallelizable_after = coerce_string_list(metadata.get("parallelizable_after", []))
        if not parallelizable_after:
            continue
        resolved_dependencies = resolve_parallelizable_dependencies(
            parallelizable_after,
            step_by_block_id=step_by_block_id,
            shared_contracts=shared_contracts,
            skeleton_step_id=skeleton_step_id,
            current_step_id=step.step_id,
        )
        if not resolved_dependencies:
            continue
        current_dependencies = [dependency for dependency in step.depends_on if dependency and dependency != step.step_id]
        if not current_dependencies:
            step.depends_on = resolved_dependencies
            continue
        if len(current_dependencies) == 1 and current_dependencies[0] not in resolved_dependencies:
            current_dependency_index = step_index.get(current_dependencies[0], -1)
            step_position = step_index.get(step.step_id, -1)
            if 0 <= current_dependency_index < step_position:
                step.depends_on = resolved_dependencies


def postprocess_generated_plan_steps(
    steps: list[ExecutionStep],
    *,
    planner_outline: str,
    execution_mode: str,
) -> list[ExecutionStep]:
    if not steps or not planner_outline.strip():
        return steps
    outline = parse_planner_outline_payload(planner_outline)
    if not outline:
        return steps
    outline_blocks = planner_outline_blocks(outline)
    if not outline_blocks:
        return steps

    processed_steps = [deepcopy(step) for step in steps]
    step_by_block_id: dict[str, str] = {}
    shared_contracts = planner_outline_shared_contracts(outline)

    for step in processed_steps:
        block = match_step_to_planner_outline_block(step, outline_blocks)
        metadata = deepcopy(step.metadata) if isinstance(step.metadata, dict) else {}
        if block:
            if block.block_id and not str(metadata.get("candidate_block_id", "")).strip():
                metadata["candidate_block_id"] = block.block_id
            if block.parallelizable_after and not coerce_string_list(metadata.get("parallelizable_after", [])):
                metadata["parallelizable_after"] = list(block.parallelizable_after)
            if block.candidate_owned_paths and not coerce_string_list(metadata.get("candidate_owned_paths", [])):
                metadata["candidate_owned_paths"] = list(block.candidate_owned_paths)
            if block.implementation_notes and not str(metadata.get("implementation_notes", "")).strip():
                metadata["implementation_notes"] = block.implementation_notes
            if block.is_skeleton_contract:
                metadata["is_skeleton_contract"] = True
                contract_docstring = block.skeleton_contract_docstring.strip()
                if contract_docstring and not str(metadata.get("skeleton_contract_docstring", "")).strip():
                    metadata["skeleton_contract_docstring"] = contract_docstring
                step.codex_description = apply_skeleton_contract_docstring(
                    step.codex_description or step.display_description or step.title,
                    contract_docstring,
                )
            step.metadata = metadata
            if block.block_id:
                step_by_block_id[block.block_id] = step.step_id
        else:
            step.metadata = metadata

        if execution_mode == "parallel" and not step.owned_paths:
            step.owned_paths = normalize_owned_paths(step.metadata.get("candidate_owned_paths", []))

    if execution_mode == "parallel":
        repack_parallelizable_steps(
            processed_steps,
            step_by_block_id=step_by_block_id,
            shared_contracts=shared_contracts,
        )
    return processed_steps


def materialize_generated_step_models(
    steps: list[ExecutionStep],
    runtime: RuntimeOptions,
) -> list[ExecutionStep]:
    if str(getattr(runtime, "model_provider", "") or "").strip().lower() != "ensemble":
        return steps

    materialized: list[ExecutionStep] = []
    for step in steps:
        next_step = deepcopy(step)
        choice = resolve_step_model_choice(next_step, runtime)
        metadata = deepcopy(next_step.metadata) if isinstance(next_step.metadata, dict) else {}
        if not next_step.model_provider:
            next_step.model_provider = choice.provider
        if not next_step.model:
            next_step.model = choice.model
        if "model_selection_source" not in metadata:
            metadata["model_selection_source"] = choice.source
        if "model_selection_reason" not in metadata:
            metadata["model_selection_reason"] = choice.reason
        next_step.metadata = metadata
        materialized.append(next_step)
    return materialized


def normalize_parallel_step_metadata(
    raw_id: str,
    metadata: dict[str, object],
    id_map: dict[str, str],
) -> dict[str, object]:
    normalized = deepcopy(metadata) if isinstance(metadata, dict) else {}
    if "merge_from" not in normalized:
        return normalized
    mapped_merge_from: list[str] = []
    seen_refs: set[str] = set()
    for item in coerce_string_list(normalized.get("merge_from", [])):
        ref = str(item).strip()
        if not ref:
            continue
        if ref not in id_map:
            raise ValueError(f"Unknown merge_from reference: {ref}")
        mapped_ref = id_map[ref]
        if mapped_ref == id_map[raw_id]:
            raise ValueError(f"{raw_id} cannot merge from itself.")
        if mapped_ref in seen_refs:
            continue
        seen_refs.add(mapped_ref)
        mapped_merge_from.append(mapped_ref)
    normalized["merge_from"] = mapped_merge_from
    return normalized


def reduce_redundant_parallel_dependencies(steps: list[ExecutionStep]) -> None:
    step_by_id = {step.step_id: step for step in steps}
    dependency_cache: dict[str, set[str]] = {}

    def dependency_closure(step_id: str, visiting: set[str]) -> set[str]:
        cached = dependency_cache.get(step_id)
        if cached is not None:
            return cached
        if step_id in visiting:
            return set()
        step = step_by_id.get(step_id)
        if step is None:
            dependency_cache[step_id] = set()
            return dependency_cache[step_id]
        next_visiting = set(visiting)
        next_visiting.add(step_id)
        closure: set[str] = set()
        for dependency in step.depends_on:
            if dependency not in step_by_id:
                continue
            closure.add(dependency)
            closure.update(dependency_closure(dependency, next_visiting))
        dependency_cache[step_id] = closure
        return closure

    for step in steps:
        if len(step.depends_on) < 2:
            continue
        redundant_dependencies = {
            dependency
            for dependency in step.depends_on
            if any(
                dependency in dependency_closure(other_dependency, set())
                for other_dependency in step.depends_on
                if other_dependency != dependency
            )
        }
        if redundant_dependencies:
            step.depends_on = [dependency for dependency in step.depends_on if dependency not in redundant_dependencies]


def plan_uses_dag_parallelism(steps: list[ExecutionStep]) -> bool:
    return any(step.depends_on or step.owned_paths for step in steps)


def validate_parallel_execution_steps(steps: list[ExecutionStep]) -> None:
    step_ids = {step.step_id for step in steps}
    indegree = {step.step_id: 0 for step in steps}
    edges: dict[str, list[str]] = {step.step_id: [] for step in steps}
    for step in steps:
        for dependency in step.depends_on:
            if dependency not in step_ids:
                raise ValueError(f"Unknown dependency reference: {dependency}")
            if dependency == step.step_id:
                raise ValueError(f"{step.step_id} cannot depend on itself.")
            indegree[step.step_id] += 1
            edges[dependency].append(step.step_id)
    ready = [step.step_id for step in steps if indegree[step.step_id] == 0]
    visited = 0
    while ready:
        current = ready.pop(0)
        visited += 1
        for neighbor in edges[current]:
            indegree[neighbor] -= 1
            if indegree[neighbor] == 0:
                ready.append(neighbor)
    if visited != len(steps):
        cycle = find_parallel_dependency_cycle(steps)
        if cycle:
            raise ValueError(f"Parallel execution plan contains a dependency cycle: {' -> '.join(cycle)}.")
        raise ValueError("Parallel execution plan contains a dependency cycle.")


def find_parallel_dependency_cycle(steps: list[ExecutionStep]) -> list[str]:
    step_ids = {step.step_id for step in steps}
    dependencies = {
        step.step_id: [dependency for dependency in step.depends_on if dependency in step_ids]
        for step in steps
    }
    visit_state: dict[str, int] = {}
    path: list[str] = []

    def visit(step_id: str) -> list[str]:
        state = visit_state.get(step_id, 0)
        if state == 1:
            if step_id in path:
                cycle_start = path.index(step_id)
                return path[cycle_start:] + [step_id]
            return [step_id, step_id]
        if state == 2:
            return []
        visit_state[step_id] = 1
        path.append(step_id)
        for dependency in dependencies.get(step_id, []):
            cycle = visit(dependency)
            if cycle:
                return cycle
        path.pop()
        visit_state[step_id] = 2
        return []

    for step in steps:
        cycle = visit(step.step_id)
        if cycle:
            return cycle
    return []


def dag_ready_batches(
    ready_steps: list[ExecutionStep],
    *,
    step_kind: Callable[[ExecutionStep], str],
) -> list[list[ExecutionStep]]:
    batches: list[list[ExecutionStep]] = []
    current_batch: list[ExecutionStep] = []
    current_paths: list[str] = []
    for step in ready_steps:
        if step_kind(step) in {"join", "barrier"}:
            if current_batch:
                batches.append(current_batch)
                current_batch = []
                current_paths = []
            batches.append([step])
            continue
        if not step.owned_paths:
            if current_batch:
                batches.append(current_batch)
                current_batch = []
                current_paths = []
            batches.append([step])
            continue
        conflict = any(
            owned_paths_conflict(candidate_path, existing_path)
            for candidate_path in step.owned_paths
            for existing_path in current_paths
        )
        if conflict and current_batch:
            batches.append(current_batch)
            current_batch = [step]
            current_paths = list(step.owned_paths)
            continue
        current_batch.append(step)
        current_paths.extend(step.owned_paths)
    if current_batch:
        batches.append(current_batch)
    return batches or [[step] for step in ready_steps]


def owned_paths_overlap_level(left: str, right: str) -> str:
    normalized_left = normalize_owned_path(left).lower()
    normalized_right = normalize_owned_path(right).lower()
    if not normalized_left or not normalized_right:
        return "none"
    if normalized_left == normalized_right:
        return "hard"
    if normalized_left.startswith(f"{normalized_right}/") or normalized_right.startswith(f"{normalized_left}/"):
        return "soft"
    return "none"


def owned_paths_conflict(left: str, right: str) -> bool:
    return owned_paths_overlap_level(left, right) == "hard"


def pending_execution_batches(
    plan_state: ExecutionPlanState,
    *,
    normalized_execution_mode: str,
    step_kind: Callable[[ExecutionStep], str],
) -> list[list[ExecutionStep]]:
    remaining = [step for step in plan_state.steps if step.status != "completed"]
    if not remaining:
        return []
    if normalized_execution_mode != "parallel":
        return [[step] for step in remaining]
    if plan_uses_dag_parallelism(plan_state.steps):
        completed_ids = {step.step_id for step in plan_state.steps if step.status == "completed"}
        ready = [
            step
            for step in plan_state.steps
            if step.status != "completed"
            and all(dep in completed_ids for dep in step.depends_on)
        ]
        if not ready:
            raise RuntimeError("No dependency-ready execution step is available. Check the DAG dependencies for cycles or blocked nodes.")
        return dag_ready_batches(ready, step_kind=step_kind)

    batches: list[list[ExecutionStep]] = []
    index = 0
    while index < len(remaining):
        current = remaining[index]
        group = current.parallel_group.strip()
        if not group:
            batches.append([current])
            index += 1
            continue
        batch = [current]
        index += 1
        while index < len(remaining) and remaining[index].parallel_group.strip() == group:
            batch.append(remaining[index])
            index += 1
        batches.append(batch)
    return batches
