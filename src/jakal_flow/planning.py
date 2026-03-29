from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .model_selection import normalize_reasoning_effort
from .models import CandidateTask, Checkpoint, ExecutionPlanState, ExecutionStep, ProjectContext
from .step_models import planning_model_selection_guidance, resolve_step_model_choice
from .utils import compact_text, normalize_workflow_mode, now_utc_iso, parse_json_text, read_text, similarity_score, svg_text_element, tokenize, wrap_svg_text, write_text


@dataclass(slots=True)
class PlanItem:
    item_id: str
    text: str


PLAN_DECOMPOSITION_PARALLEL_PROMPT_FILENAME = "PLAN_DECOMPOSITION_PARALLEL_PROMPT.txt"
ML_PLAN_DECOMPOSITION_PROMPT_FILENAME = "ML_PLAN_DECOMPOSITION_PROMPT.txt"
PLAN_GENERATION_PARALLEL_PROMPT_FILENAME = "PLAN_GENERATION_PARALLEL_PROMPT.txt"
PLAN_GENERATION_PROMPT_FILENAME = PLAN_GENERATION_PARALLEL_PROMPT_FILENAME
STEP_EXECUTION_PARALLEL_PROMPT_FILENAME = "STEP_EXECUTION_PARALLEL_PROMPT.txt"
STEP_EXECUTION_PROMPT_FILENAME = STEP_EXECUTION_PARALLEL_PROMPT_FILENAME
DEBUGGER_PARALLEL_PROMPT_FILENAME = "DEBUGGER_PARALLEL_PROMPT.txt"
DEBUGGER_PROMPT_FILENAME = DEBUGGER_PARALLEL_PROMPT_FILENAME
MERGER_PARALLEL_PROMPT_FILENAME = "MERGER_PARALLEL_PROMPT.txt"
FINALIZATION_PROMPT_FILENAME = "FINALIZATION_PROMPT.txt"
OPTIMIZATION_PROMPT_FILENAME = "OPTIMIZATION_PROMPT.txt"
ML_PLAN_GENERATION_PROMPT_FILENAME = "ML_PLAN_GENERATION_PROMPT.txt"
ML_STEP_EXECUTION_PROMPT_FILENAME = "ML_STEP_EXECUTION_PROMPT.txt"
ML_FINALIZATION_PROMPT_FILENAME = "ML_FINALIZATION_PROMPT.txt"
SCOPE_GUARD_TEMPLATE_FILENAME = "SCOPE_GUARD_TEMPLATE.md"
REFERENCE_GUIDE_FILENAME = "REFERENCE_GUIDE.md"
REFERENCE_GUIDE_DISPLAY_PATH = f"src/jakal_flow/docs/{REFERENCE_GUIDE_FILENAME}"


def source_docs_dir() -> Path:
    return Path(__file__).resolve().parent / "docs"


def source_prompt_template_path(name: str) -> Path:
    return source_docs_dir() / name


@lru_cache(maxsize=None)
def load_source_prompt_template(name: str) -> str:
    return source_prompt_template_path(name).read_text(encoding="utf-8")


def _normalize_execution_mode(value: str | None) -> str:
    return "parallel"


def plan_generation_prompt_filename(execution_mode: str | None, workflow_mode: str | None = None) -> str:
    if normalize_workflow_mode(workflow_mode) == "ml":
        return ML_PLAN_GENERATION_PROMPT_FILENAME
    _normalize_execution_mode(execution_mode)
    return PLAN_GENERATION_PARALLEL_PROMPT_FILENAME


def plan_decomposition_prompt_filename(execution_mode: str | None, workflow_mode: str | None = None) -> str:
    if normalize_workflow_mode(workflow_mode) == "ml":
        return ML_PLAN_DECOMPOSITION_PROMPT_FILENAME
    _normalize_execution_mode(execution_mode)
    return PLAN_DECOMPOSITION_PARALLEL_PROMPT_FILENAME


def step_execution_prompt_filename(execution_mode: str | None, workflow_mode: str | None = None) -> str:
    if normalize_workflow_mode(workflow_mode) == "ml":
        return ML_STEP_EXECUTION_PROMPT_FILENAME
    _normalize_execution_mode(execution_mode)
    return STEP_EXECUTION_PARALLEL_PROMPT_FILENAME


def load_plan_generation_prompt_template(execution_mode: str | None, workflow_mode: str | None = None) -> str:
    return load_source_prompt_template(plan_generation_prompt_filename(execution_mode, workflow_mode))


def load_plan_decomposition_prompt_template(execution_mode: str | None, workflow_mode: str | None = None) -> str:
    return load_source_prompt_template(plan_decomposition_prompt_filename(execution_mode, workflow_mode))


def load_step_execution_prompt_template(execution_mode: str | None, workflow_mode: str | None = None) -> str:
    return load_source_prompt_template(step_execution_prompt_filename(execution_mode, workflow_mode))


def debugger_prompt_filename(execution_mode: str | None) -> str:
    _normalize_execution_mode(execution_mode)
    return DEBUGGER_PARALLEL_PROMPT_FILENAME


def load_debugger_prompt_template(execution_mode: str | None) -> str:
    return load_source_prompt_template(debugger_prompt_filename(execution_mode))


def merger_prompt_filename(execution_mode: str | None) -> str:
    _normalize_execution_mode(execution_mode)
    return MERGER_PARALLEL_PROMPT_FILENAME


def load_merger_prompt_template(execution_mode: str | None) -> str:
    return load_source_prompt_template(merger_prompt_filename(execution_mode))


def finalization_prompt_filename(workflow_mode: str | None = None) -> str:
    if normalize_workflow_mode(workflow_mode) == "ml":
        return ML_FINALIZATION_PROMPT_FILENAME
    return FINALIZATION_PROMPT_FILENAME


def load_finalization_prompt_template(workflow_mode: str | None = None) -> str:
    return load_source_prompt_template(finalization_prompt_filename(workflow_mode))


def load_optimization_prompt_template() -> str:
    return load_source_prompt_template(OPTIMIZATION_PROMPT_FILENAME)


@lru_cache(maxsize=1)
def load_reference_guide_text() -> str:
    text = read_text(source_prompt_template_path(REFERENCE_GUIDE_FILENAME))
    return compact_text(text, 2200) or f"{REFERENCE_GUIDE_DISPLAY_PATH} not found."


def _summarize_source_inventory(repo_dir: Path, limit: int = 10) -> str:
    roots = [
        repo_dir / "src",
        repo_dir / "app",
        repo_dir / "lib",
        repo_dir / "desktop" / "src",
    ]
    allowed_suffixes = {
        ".c",
        ".cc",
        ".cpp",
        ".cs",
        ".go",
        ".h",
        ".hpp",
        ".java",
        ".js",
        ".jsx",
        ".kt",
        ".m",
        ".mm",
        ".php",
        ".py",
        ".rb",
        ".rs",
        ".scala",
        ".sh",
        ".swift",
        ".ts",
        ".tsx",
    }
    excluded_parts = {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".venv",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "node_modules",
        "target",
        "venv",
    }
    samples: list[str] = []
    seen: set[str] = set()
    total = 0

    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in allowed_suffixes:
                continue
            if any(part in excluded_parts for part in path.parts):
                continue
            relative = str(path.relative_to(repo_dir)).replace("\\", "/")
            if relative in seen:
                continue
            seen.add(relative)
            total += 1
            if len(samples) < limit:
                samples.append(relative)

    if not total:
        return (
            "No obvious implementation files detected under src/, app/, lib/, or desktop/src. "
            "A narrow skeleton/bootstrap step is acceptable only if it establishes the first real contract, "
            "entrypoint, or module."
        )

    suffix = "" if total <= limit else f", plus {total - limit} more"
    return (
        "Existing implementation files detected. Prefer extending or editing these paths instead of adding "
        f"scaffold-only skeleton steps unless a genuinely new boundary is required: {', '.join(samples)}{suffix}."
    )


def _summarize_docs_inventory(
    repo_dir: Path,
    *,
    max_files: int = 8,
    max_chars_per_file: int = 320,
    max_total_chars: int = 2400,
) -> str:
    docs_dir = repo_dir / "docs"
    if not docs_dir.exists():
        return "No markdown files under repo/docs."
    doc_paths = sorted(docs_dir.rglob("*.md"))
    if not doc_paths:
        return "No markdown files under repo/docs."

    entries: list[str] = []
    current_chars = 0
    for path in doc_paths:
        if len(entries) >= max_files or current_chars >= max_total_chars:
            break
        entry = f"## {path.relative_to(repo_dir)}\n{compact_text(read_text(path), max_chars_per_file)}"
        if entries and current_chars + len(entry) + 2 > max_total_chars:
            break
        entries.append(entry)
        current_chars += len(entry) + 2

    if not entries:
        first_path = doc_paths[0]
        entries.append(f"## {first_path.relative_to(repo_dir)}\n{compact_text(read_text(first_path), max_chars_per_file)}")

    omitted_count = max(0, len(doc_paths) - len(entries))
    if omitted_count:
        entries.append(f"... {omitted_count} more markdown doc file(s) omitted to keep planning context compact.")
    return "\n\n".join(entries)


def scan_repository_inputs(repo_dir: Path) -> dict[str, str]:
    readme = read_text(repo_dir / "README.md")
    agents = repository_agents_summary(repo_dir)
    return {
        "readme": compact_text(readme, 2000) or "README.md not found.",
        "agents": agents,
        "docs": _summarize_docs_inventory(repo_dir),
        "source": _summarize_source_inventory(repo_dir),
    }


def repository_agents_summary(repo_dir: Path, *, max_chars: int = 1500) -> str:
    agents = read_text(repo_dir / "AGENTS.md")
    return compact_text(agents, max_chars) or "AGENTS.md not found."


def compact_repository_inputs(
    repo_inputs: dict[str, str],
    *,
    readme_chars: int = 1200,
    agents_chars: int = 1000,
    docs_chars: int = 1800,
    source_chars: int = 900,
) -> dict[str, str]:
    return {
        "readme": compact_text(repo_inputs.get("readme", ""), readme_chars) or "README.md not found.",
        "agents": compact_text(repo_inputs.get("agents", ""), agents_chars) or "AGENTS.md not found.",
        "docs": compact_text(repo_inputs.get("docs", ""), docs_chars) or "No markdown files under repo/docs.",
        "source": compact_text(repo_inputs.get("source", ""), source_chars) or "Source inventory unavailable.",
    }


def followup_planning_repository_inputs(repo_inputs: dict[str, str]) -> dict[str, str]:
    return compact_repository_inputs(
        repo_inputs,
        readme_chars=900,
        agents_chars=900,
        docs_chars=1400,
        source_chars=750,
    )


def _candidate_owned_paths_from_source_summary(source_summary: str, limit: int = 4) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    for match in re.findall(r"(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+", source_summary or ""):
        normalized = match.strip().rstrip(".,")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        candidates.append(normalized)
        if len(candidates) >= max(1, limit):
            break
    return candidates


def build_fast_planner_outline(
    repo_inputs: dict[str, str],
    user_prompt: str,
) -> str:
    source_summary = repo_inputs.get("source", "")
    candidate_owned_paths = _candidate_owned_paths_from_source_summary(source_summary)
    prompt_summary = compact_text(user_prompt.strip(), 180) or "Implement the requested repository change safely."
    payload = {
        "title": compact_text(prompt_summary, 80) or "Fast planning outline",
        "strategy_summary": (
            "Fast planning mode: skip the separate decomposition pass, keep the DAG narrow, and prefer direct edits "
            "to existing implementation surfaces before introducing new scaffolding."
        ),
        "shared_contracts": [],
        "skeleton_step": {
            "block_id": "SK1",
            "needed": False,
            "task_title": "",
            "purpose": "",
            "contract_docstring": "",
            "candidate_owned_paths": [],
            "success_criteria": "",
        },
        "candidate_blocks": [
            {
                "block_id": "B1",
                "goal": prompt_summary,
                "work_items": [
                    "Identify the smallest safe implementation slice that directly satisfies the user request.",
                    "Reuse or extend existing modules before creating new boundaries.",
                    "Preserve verification and traceability artifacts while shaping the final DAG.",
                ],
                "implementation_notes": (
                    "Use the repository summary to keep file ownership narrow. Prefer edits to existing code paths "
                    "and let Planner Agent B split the work further only when there are truly independent outcomes."
                ),
                "testable_boundary": "The final execution plan maps the request onto small, locally judgeable checkpoints.",
                "candidate_owned_paths": candidate_owned_paths,
                "parallelizable_after": [],
                "parallel_notes": "Only create a parallel-ready wave when the owned paths stay narrow and non-overlapping.",
            }
        ],
        "packing_notes": [
            "Preserve any directly relevant AGENTS.md constraints and existing repository structure.",
            "Favor a minimal prerequisite step only when a shared contract or entrypoint clearly needs to be frozen first.",
            "Keep the resulting plan compact enough for fast iteration while still being handoff-quality.",
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def assess_repository_maturity(repo_dir: Path, repo_inputs: dict[str, str]) -> tuple[bool, dict[str, int]]:
    score = 0
    details = {"readme": 0, "docs": 0, "source": 0, "tests": 0}
    if "not found" not in repo_inputs["readme"].lower():
        score += 1
        details["readme"] = 1
    if "no markdown files under repo/docs" not in repo_inputs["docs"].lower():
        score += 1
        details["docs"] = 1
    source_summary = repo_inputs.get("source", "")
    if source_summary and "no obvious implementation files detected" not in source_summary.lower():
        score += 1
        details["source"] = 1
    tests_dir = repo_dir / "tests"
    if tests_dir.exists() or list(repo_dir.glob("*test*")):
        score += 1
        details["tests"] = 1
    return score >= 2, details


def generate_project_plan(context: ProjectContext, repo_inputs: dict[str, str]) -> str:
    repo_name = context.metadata.repo_url.rstrip("/").split("/")[-1].removesuffix(".git")
    seed_goals = _derive_seed_goals(repo_inputs)
    reference_notes = load_reference_guide_text()
    lines = [
        "# Project Plan",
        "",
        f"- Repository: {repo_name}",
        f"- Source: {context.metadata.repo_url}",
        f"- Branch: {context.metadata.branch}",
        f"- Generated at: {now_utc_iso()}",
        "",
        "## Repository Context",
        "### README",
        repo_inputs["readme"],
        "",
        "### AGENTS",
        repo_inputs["agents"],
        "",
        "### Source Inventory",
        repo_inputs.get("source", "Source inventory unavailable."),
        "",
        "### Reference Notes",
        reference_notes,
        "",
        "### Docs",
        repo_inputs["docs"],
        "",
        "## Focus Areas",
        f"- PL1: {seed_goals[0]}",
        f"- PL2: {seed_goals[1]}",
        f"- PL3: {seed_goals[2]}",
        "",
        "## Non-Goals",
        "- Do not expand scope beyond the requested repository changes.",
        "- Do not update docs ahead of verified implementation.",
        "",
        "## Operating Constraints",
        "- Prefer small, reversible changes with direct tests.",
        "- Keep repository naming and structure consistent with the existing codebase.",
        "",
    ]
    return "\n".join(lines)


def is_plan_markdown(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    lowered = normalized.lower()
    if lowered.startswith("# project plan") or lowered.startswith("# execution plan"):
        return True
    plan_ids = re.findall(r"\b(?:PL|ST)\d+\b", normalized)
    return len(plan_ids) >= 2


def bootstrap_plan_prompt(context: ProjectContext, repo_inputs: dict[str, str], user_prompt: str) -> str:
    reference_notes = load_reference_guide_text()
    source_summary = repo_inputs.get("source", "Source inventory unavailable.")
    return "\n".join(
        [
            "Draft a project plan in markdown and write it to the managed planning file outside the repo.",
            f"Target file: {context.paths.plan_file}",
            "The repository is early-stage or insufficiently documented, so the plan must be prompt-based.",
            "Use the following priority order while planning:",
            "1. Follow AGENTS.md and explicit repository constraints first.",
            "2. Use the user's prompt as the primary product direction within those constraints.",
            f"3. Use {REFERENCE_GUIDE_DISPLAY_PATH} for unstated implementation preferences and tie-breakers.",
            "4. Use README.md and other repository docs to align with existing structure and terminology.",
            "5. Fall back to generic defaults only when the repository sources above do not decide the issue.",
            "Keep the plan concrete, scoped, and testable.",
            "Prefer a finished, handoff-quality implementation over a narrow MVP slice.",
            "Add directly necessary setup, integration, validation, cleanup, documentation, polish, and supporting implementation work even if the user did not spell out each item.",
            "Do not invent speculative roadmap items or optional expansion beyond the requested product scope.",
            "",
            "Repository context:",
            f"- Repo URL: {context.metadata.repo_url}",
            f"- Branch: {context.metadata.branch}",
            "",
            "Observed repository inputs:",
            f"README:\n{repo_inputs['readme']}",
            "",
            f"AGENTS:\n{repo_inputs['agents']}",
            "",
            f"Source inventory:\n{source_summary}",
            "",
            f"{REFERENCE_GUIDE_DISPLAY_PATH}:\n{reference_notes}",
            "",
            f"docs summary:\n{repo_inputs['docs']}",
            "",
            "User initialization prompt:",
            user_prompt.strip(),
            "",
            "Required plan structure:",
            "- Title: Project Plan",
            "- Repository metadata",
            "- Focus areas as PL1, PL2, PL3...",
            "- Non-goals",
            "- Operating constraints",
            "",
            "Write the file directly. Keep it realistic and implementation-oriented.",
        ]
    )


def _derive_seed_goals(repo_inputs: dict[str, str]) -> list[str]:
    text = " ".join(repo_inputs.values()).lower()
    goals = [
        "Stabilize the existing codebase with reproducible tests and small, reversible improvements.",
        "Improve internal structure, typing, and automation without expanding the product scope.",
        "Update documentation only when implementation changes are verified and already present in the repository.",
    ]
    if "cli" in text:
        goals[0] = "Harden CLI behavior, error handling, and test coverage without widening the command surface unnecessarily."
    if "api" in text or "http" in text:
        goals[1] = "Improve API correctness, validation, and operational safety before adding new endpoint behavior."
    return goals


def ensure_scope_guard(context: ProjectContext) -> str:
    template = load_source_prompt_template(SCOPE_GUARD_TEMPLATE_FILENAME)
    return template.format(
        repo_url=context.metadata.repo_url,
        branch=context.metadata.branch,
        repo_slug=context.metadata.slug,
    )


def extract_plan_items(plan_text: str) -> list[PlanItem]:
    items: list[PlanItem] = []
    for line in plan_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = re.match(r"[-*]\s+\[[ xX]\]\s+((?P<id>[A-Z]{2,}\d+):\s+)?(?P<body>.+)", stripped)
        if match:
            item_id = match.group("id") or f"PL{len(items) + 1}"
            items.append(PlanItem(item_id=item_id, text=match.group("body").strip()))
            continue
        match = re.match(r"[-*]\s+(?P<id>[A-Z]{2,}\d+):\s+(?P<body>.+)", stripped)
        if match and len(tokenize(match.group("body"))) >= 3:
            item_id = match.group("id")
            items.append(PlanItem(item_id=item_id, text=match.group("body").strip()))
    deduped: list[PlanItem] = []
    seen: set[str] = set()
    for item in items:
        key = f"{item.item_id}|{item.text}"
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped[:20]


def build_mid_term_plan(plan_text: str, limit: int = 5) -> tuple[str, list[PlanItem]]:
    items = extract_plan_items(plan_text)
    positive_items = [item for item in items if not item.text.lower().startswith("do not")]
    chosen = positive_items[:limit] if positive_items else []
    lines = [
        "# Mid-Term Plan",
        "",
        "This plan is regenerated only at block boundaries and must remain a strict subset of the saved project plan.",
        "",
    ]
    if not chosen:
        lines.append("- [ ] MT1: Establish a verified, low-risk maintenance task based on the current repository state.")
        return "\n".join(lines) + "\n", []
    for index, item in enumerate(chosen, start=1):
        lines.append(f"- [ ] MT{index} -> {item.item_id}: {item.text}")
    lines.append("")
    return "\n".join(lines), chosen


def build_mid_term_plan_from_user_items(items: list[str]) -> tuple[str, list[PlanItem]]:
    cleaned = [item.strip() for item in items if item.strip()]
    plan_items = [PlanItem(item_id=f"UT{index}", text=item) for index, item in enumerate(cleaned, start=1)]
    return build_mid_term_plan_from_plan_items(
        plan_items,
        "This plan was provided or edited by the user and is used as the current block sequence.",
    )


def build_mid_term_plan_from_plan_items(items: list[PlanItem], description: str) -> tuple[str, list[PlanItem]]:
    lines = [
        "# Mid-Term Plan",
        "",
        description,
        "",
    ]
    if not items:
        lines.append("- [ ] MT1: Establish a verified, low-risk maintenance task based on the current repository state.")
        return "\n".join(lines) + "\n", []
    for index, item in enumerate(items, start=1):
        lines.append(f"- [ ] MT{index} -> {item.item_id}: {item.text}")
    lines.append("")
    return "\n".join(lines), items


def validate_mid_term_subset(mid_term_text: str, plan_text: str) -> tuple[bool, list[str]]:
    plan_ids = {item.item_id for item in extract_plan_items(plan_text)}
    violations: list[str] = []
    for line in mid_term_text.splitlines():
        match = re.search(r"->\s*([A-Z]{2,}\d+)", line)
        if match and match.group(1) not in plan_ids:
            violations.append(line.strip())
    return not violations, violations


def candidate_tasks_from_mid_term(mid_items: list[PlanItem], memory_context: str) -> list[CandidateTask]:
    tasks: list[CandidateTask] = []
    for index, item in enumerate(mid_items[:3], start=1):
        rationale = f"Derived from {item.item_id}. Favor a small reversible change with direct test coverage."
        score = 1.0 + max(0.0, 0.2 - similarity_score(item.text, memory_context))
        tasks.append(
            CandidateTask(
                candidate_id=f"C{index}",
                title=item.text,
                rationale=rationale,
                plan_refs=[item.item_id],
                score=score,
            )
        )
    if not tasks:
        tasks.append(
            CandidateTask(
                candidate_id="C1",
                title="Stabilize one narrow, testable issue already present in the repository",
                rationale="Fallback task when the saved plan is not machine-readable.",
                plan_refs=[],
                score=0.5,
            )
        )
    return tasks


def work_breakdown_prompt(
    context: ProjectContext,
    repo_inputs: dict[str, str],
    plan_text: str,
    memory_context: str,
    max_items: int,
) -> str:
    reference_notes = load_reference_guide_text()
    return "\n".join(
        [
            f"You are planning work for the managed repository at {context.paths.repo_dir}.",
            "Follow any AGENTS.md rules in the repository.",
            "Break the work into small, implementation-oriented blocks that stay within the current repository.",
            "Prefer tasks that can be completed with strict verification and a rollback-safe commit.",
            "Do not propose broad roadmap items or vague research-only work.",
            f"Return exactly one JSON object with a top-level 'tasks' array containing at most {max(1, max_items)} items.",
            "Each task must be an object with:",
            '- "title": short actionable task title',
            '- "primary_ref": matching plan id such as PL1 when possible, otherwise use ""',
            '- "reason": one short sentence',
            "Do not include markdown fences or any text outside the JSON object.",
            "",
            "Repository summary:",
            f"README:\n{repo_inputs['readme']}",
            "",
            f"AGENTS:\n{repo_inputs['agents']}",
            "",
            "Planning priority order:",
            "1. Follow AGENTS.md and explicit repository constraints first.",
            "2. Use the user request as the primary product goal within those constraints.",
            f"3. Use {REFERENCE_GUIDE_DISPLAY_PATH} for unstated implementation preferences and tie-breakers.",
            "4. Use README.md and other repository docs to align with the existing structure.",
            "5. Fall back to generic defaults only if the repository sources above do not decide the issue.",
            "",
            f"Reference notes ({REFERENCE_GUIDE_DISPLAY_PATH}):\n{reference_notes}",
            "",
            f"Docs:\n{repo_inputs['docs']}",
            "",
            "Current plan snapshot:",
            compact_text(plan_text, 5000),
            "",
            "Memory context:",
            compact_text(memory_context, 2500),
        ]
    )


def prompt_to_execution_plan_prompt(
    context: ProjectContext,
    repo_inputs: dict[str, str],
    user_prompt: str,
    max_steps: int,
    execution_mode: str = "parallel",
    planner_outline: str = "",
    template_text: str | None = None,
) -> str:
    runtime = getattr(context, "runtime", None)
    workflow_mode = normalize_workflow_mode(getattr(runtime, "workflow_mode", "standard"))
    template = template_text or load_plan_generation_prompt_template(execution_mode, workflow_mode)
    compact_inputs = followup_planning_repository_inputs(repo_inputs)
    try:
        return template.format(
            repo_dir=context.paths.repo_dir,
            max_steps=max(3, max_steps),
            workflow_mode=workflow_mode,
            execution_mode=_normalize_execution_mode(execution_mode),
            readme=compact_inputs["readme"],
            agents=compact_inputs["agents"],
            reference_notes=load_reference_guide_text(),
            docs=compact_inputs["docs"],
            source=compact_inputs["source"],
            user_prompt=user_prompt.strip(),
            planner_outline=compact_text(planner_outline.strip(), 4000) or "Planner Agent A output unavailable.",
            model_selection_guidance=planning_model_selection_guidance(runtime),
        )
    except KeyError as exc:
        raise ValueError(f"Unknown placeholder in plan generation prompt template: {exc.args[0]}") from exc


def prompt_to_plan_decomposition_prompt(
    context: ProjectContext,
    repo_inputs: dict[str, str],
    user_prompt: str,
    max_steps: int,
    execution_mode: str = "parallel",
    template_text: str | None = None,
) -> str:
    runtime = getattr(context, "runtime", None)
    workflow_mode = normalize_workflow_mode(getattr(runtime, "workflow_mode", "standard"))
    template = template_text or load_plan_decomposition_prompt_template(execution_mode, workflow_mode)
    try:
        return template.format(
            repo_dir=context.paths.repo_dir,
            max_steps=max(3, max_steps),
            workflow_mode=workflow_mode,
            execution_mode=_normalize_execution_mode(execution_mode),
            readme=repo_inputs["readme"],
            agents=repo_inputs["agents"],
            reference_notes=load_reference_guide_text(),
            docs=repo_inputs["docs"],
            source=repo_inputs.get("source", "Source inventory unavailable."),
            user_prompt=user_prompt.strip(),
        )
    except KeyError as exc:
        raise ValueError(f"Unknown placeholder in plan decomposition prompt template: {exc.args[0]}") from exc


def parse_execution_plan_response(
    response_text: str,
    default_test_command: str,
    default_reasoning_effort: str,
    limit: int = 8,
) -> tuple[str, str, list[ExecutionStep]]:
    raw = response_text.strip()
    if not raw:
        return "", "", []
    try:
        payload = parse_json_text(raw)
    except json.JSONDecodeError:
        return "", "", []

    plan_title = ""
    summary = ""
    tasks_payload: object = []
    if isinstance(payload, dict):
        plan_title = str(payload.get("title", "")).strip()
        summary = str(payload.get("summary", "")).strip()
        tasks_payload = payload.get("tasks", payload.get("steps", []))
    elif isinstance(payload, list):
        tasks_payload = payload
    if not isinstance(tasks_payload, list):
        return plan_title, summary, []

    fallback_effort = normalize_reasoning_effort(default_reasoning_effort, fallback="high")
    steps: list[ExecutionStep] = []
    seen: set[str] = set()
    for index, item in enumerate(tasks_payload, start=1):
        if len(steps) >= max(1, limit):
            break
        if not isinstance(item, dict):
            continue
        title = str(item.get("task_title", item.get("title", ""))).strip()
        if not title:
            continue
        dedupe_key = title.lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        display_description = str(item.get("display_description", item.get("description", ""))).strip()
        codex_description = str(item.get("codex_description", "")).strip() or display_description or title
        reasoning_effort = normalize_reasoning_effort(
            str(item.get("reasoning_effort", item.get("effort", ""))),
            fallback=fallback_effort,
        )
        parallel_group = str(item.get("parallel_group", "")).strip()
        raw_dependencies = item.get("depends_on", [])
        if isinstance(raw_dependencies, list):
            depends_on = [str(value).strip() for value in raw_dependencies if str(value).strip()]
        else:
            depends_on = [part.strip() for part in str(raw_dependencies).replace("\n", ",").split(",") if part.strip()]
        raw_owned_paths = item.get("owned_paths", [])
        if isinstance(raw_owned_paths, list):
            owned_paths = [str(value).strip() for value in raw_owned_paths if str(value).strip()]
        else:
            owned_paths = [part.strip() for part in str(raw_owned_paths).replace("\n", ",").split(",") if part.strip()]
        metadata = item.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        else:
            metadata = dict(metadata)
        steps.append(
            ExecutionStep(
                step_id=str(item.get("step_id", item.get("node_id", ""))).strip() or f"ST{len(steps) + 1}",
                title=title,
                display_description=display_description,
                codex_description=codex_description,
                model_provider=str(item.get("model_provider", "")).strip().lower(),
                model=str(item.get("model", item.get("model_slug_input", ""))).strip().lower(),
                test_command=str(item.get("test_command", "")).strip() or default_test_command,
                success_criteria=str(item.get("success_criteria", "")).strip(),
                reasoning_effort=reasoning_effort,
                parallel_group=parallel_group,
                depends_on=depends_on,
                owned_paths=owned_paths,
                status="pending",
                metadata=metadata,
            )
        )
    return plan_title, summary, steps


def parse_work_breakdown_response(response_text: str, limit: int = 6) -> list[PlanItem]:
    raw = response_text.strip()
    if not raw:
        return []
    payload: object
    try:
        payload = parse_json_text(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        tasks_payload = payload.get("tasks", [])
    elif isinstance(payload, list):
        tasks_payload = payload
    else:
        return []
    if not isinstance(tasks_payload, list):
        return []

    items: list[PlanItem] = []
    seen_titles: set[str] = set()
    for index, entry in enumerate(tasks_payload, start=1):
        if len(items) >= max(1, limit):
            break
        title = ""
        item_id = ""
        if isinstance(entry, str):
            title = entry.strip()
        elif isinstance(entry, dict):
            title = str(entry.get("title", "")).strip()
            item_id = str(entry.get("primary_ref", "")).strip().upper()
        if len(tokenize(title)) < 2:
            continue
        key = title.lower()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        if not re.fullmatch(r"[A-Z]{2,}\d+", item_id):
            item_id = f"WB{index}"
        items.append(PlanItem(item_id=item_id, text=title))
    return items


def select_candidate(tasks: list[CandidateTask]) -> CandidateTask:
    return sorted(tasks, key=lambda item: item.score, reverse=True)[0]


def write_active_task(context: ProjectContext, candidate: CandidateTask, memory_context: str) -> None:
    lines = [
        "# Active Task",
        "",
        f"- Selected at: {now_utc_iso()}",
        f"- Candidate: {candidate.candidate_id}",
        f"- Scope refs: {', '.join(candidate.plan_refs) if candidate.plan_refs else 'none'}",
        "",
        "## Task",
        candidate.title,
        "",
        "## Rationale",
        candidate.rationale,
        "",
        "## Memory Context",
        memory_context,
        "",
    ]
    write_text(context.paths.active_task_file, "\n".join(lines))


def implementation_prompt(
    context: ProjectContext,
    candidate: CandidateTask,
    memory_context: str,
    pass_name: str,
    execution_step: ExecutionStep | None = None,
    template_text: str | None = None,
) -> str:
    plan_text = read_text(context.paths.plan_file)
    mid_term = read_text(context.paths.mid_term_plan_file)
    scope_guard = read_text(context.paths.scope_guard_file)
    research_notes = read_text(context.paths.research_notes_file)
    workflow_mode = normalize_workflow_mode(getattr(context.runtime, "workflow_mode", "standard"))
    template = template_text or load_step_execution_prompt_template(getattr(context.runtime, "execution_mode", "parallel"), workflow_mode)
    task_title = execution_step.title if execution_step else candidate.title
    display_description = execution_step.display_description.strip() if execution_step else ""
    codex_description = execution_step.codex_description.strip() if execution_step else ""
    test_command = context.runtime.test_cmd
    if execution_step and execution_step.test_command.strip():
        test_command = execution_step.test_command.strip()
    if not display_description:
        display_description = task_title
    if not codex_description:
        codex_description = candidate.rationale.strip() or display_description or task_title
    success_criteria = (
        execution_step.success_criteria.strip()
        if execution_step and execution_step.success_criteria.strip()
        else f"The verification command `{test_command}` exits successfully."
    )
    depends_on = ", ".join(execution_step.depends_on) if execution_step and execution_step.depends_on else "none"
    owned_paths = "\n".join(f"- {path}" for path in execution_step.owned_paths) if execution_step and execution_step.owned_paths else "- none declared"
    step_metadata = execution_step.metadata if execution_step and execution_step.metadata else {}
    agents_summary = repository_agents_summary(context.paths.repo_dir, max_chars=1200)
    try:
        return template.format(
            repo_dir=context.paths.repo_dir,
            docs_dir=context.paths.docs_dir,
            workflow_mode=workflow_mode,
            pass_name=pass_name,
            test_command=test_command,
            task_title=task_title,
            display_description=display_description,
            codex_description=codex_description,
            success_criteria=success_criteria,
            depends_on=depends_on,
            owned_paths=owned_paths,
            agents_summary=agents_summary,
            step_metadata=json.dumps(step_metadata, indent=2, sort_keys=True) if step_metadata else "{}",
            candidate_rationale=candidate.rationale,
            memory_context=memory_context,
            plan_snapshot=compact_text(plan_text, 4000),
            mid_term_plan=compact_text(mid_term, 2500),
            scope_guard=compact_text(scope_guard, 2500),
            research_notes=compact_text(research_notes, 2500),
            research_notes_file=context.paths.research_notes_file,
            ml_step_report_file=context.paths.ml_step_report_file,
            ml_experiment_report_file=context.paths.ml_experiment_report_file,
            extra_prompt=context.runtime.extra_prompt.strip() or "None.",
        )
    except KeyError as exc:
        raise ValueError(f"Unknown placeholder in step execution prompt template: {exc.args[0]}") from exc


def debugger_prompt(
    context: ProjectContext,
    candidate: CandidateTask,
    memory_context: str,
    failing_pass_name: str,
    failing_test_summary: str,
    failing_test_stdout: str,
    failing_test_stderr: str,
    execution_step: ExecutionStep | None = None,
    template_text: str | None = None,
) -> str:
    plan_text = read_text(context.paths.plan_file)
    mid_term = read_text(context.paths.mid_term_plan_file)
    scope_guard = read_text(context.paths.scope_guard_file)
    research_notes = read_text(context.paths.research_notes_file)
    template = template_text or load_debugger_prompt_template(getattr(context.runtime, "execution_mode", "parallel"))
    workflow_mode = normalize_workflow_mode(getattr(context.runtime, "workflow_mode", "standard"))
    task_title = execution_step.title if execution_step else candidate.title
    display_description = execution_step.display_description.strip() if execution_step else ""
    codex_description = execution_step.codex_description.strip() if execution_step else ""
    test_command = context.runtime.test_cmd
    if execution_step and execution_step.test_command.strip():
        test_command = execution_step.test_command.strip()
    if not display_description:
        display_description = task_title
    if not codex_description:
        codex_description = candidate.rationale.strip() or display_description or task_title
    success_criteria = (
        execution_step.success_criteria.strip()
        if execution_step and execution_step.success_criteria.strip()
        else f"The verification command `{test_command}` exits successfully."
    )
    depends_on = ", ".join(execution_step.depends_on) if execution_step and execution_step.depends_on else "none"
    owned_paths = "\n".join(f"- {path}" for path in execution_step.owned_paths) if execution_step and execution_step.owned_paths else "- none declared"
    step_metadata = execution_step.metadata if execution_step and execution_step.metadata else {}
    agents_summary = repository_agents_summary(context.paths.repo_dir, max_chars=1200)
    try:
        return template.format(
            repo_dir=context.paths.repo_dir,
            docs_dir=context.paths.docs_dir,
            workflow_mode=workflow_mode,
            failing_pass_name=failing_pass_name,
            test_command=test_command,
            task_title=task_title,
            display_description=display_description,
            codex_description=codex_description,
            success_criteria=success_criteria,
            depends_on=depends_on,
            owned_paths=owned_paths,
            agents_summary=agents_summary,
            step_metadata=json.dumps(step_metadata, indent=2, sort_keys=True) if step_metadata else "{}",
            candidate_rationale=candidate.rationale,
            memory_context=memory_context,
            plan_snapshot=compact_text(plan_text, 4000),
            mid_term_plan=compact_text(mid_term, 2500),
            scope_guard=compact_text(scope_guard, 2500),
            research_notes=compact_text(research_notes, 2500),
            research_notes_file=context.paths.research_notes_file,
            ml_step_report_file=context.paths.ml_step_report_file,
            failing_test_summary=compact_text(failing_test_summary, 1200) or "No verification summary was captured.",
            failing_test_stdout=compact_text(failing_test_stdout, 4000) or "No stdout captured.",
            failing_test_stderr=compact_text(failing_test_stderr, 4000) or "No stderr captured.",
            extra_prompt=context.runtime.extra_prompt.strip() or "None.",
        )
    except KeyError as exc:
        raise ValueError(f"Unknown placeholder in debugger prompt template: {exc.args[0]}") from exc


def merger_prompt(
    context: ProjectContext,
    candidate: CandidateTask,
    memory_context: str,
    failing_command: str,
    failing_summary: str,
    failing_stdout: str,
    failing_stderr: str,
    merge_targets: list[str] | None = None,
    execution_step: ExecutionStep | None = None,
    template_text: str | None = None,
) -> str:
    plan_text = read_text(context.paths.plan_file)
    mid_term = read_text(context.paths.mid_term_plan_file)
    scope_guard = read_text(context.paths.scope_guard_file)
    research_notes = read_text(context.paths.research_notes_file)
    template = template_text or load_merger_prompt_template(getattr(context.runtime, "execution_mode", "parallel"))
    workflow_mode = normalize_workflow_mode(getattr(context.runtime, "workflow_mode", "standard"))
    task_title = execution_step.title if execution_step else candidate.title
    display_description = execution_step.display_description.strip() if execution_step else ""
    codex_description = execution_step.codex_description.strip() if execution_step else ""
    test_command = context.runtime.test_cmd
    if execution_step and execution_step.test_command.strip():
        test_command = execution_step.test_command.strip()
    if not display_description:
        display_description = task_title
    if not codex_description:
        codex_description = candidate.rationale.strip() or display_description or task_title
    success_criteria = (
        execution_step.success_criteria.strip()
        if execution_step and execution_step.success_criteria.strip()
        else (
            "The merge conflict is resolved cleanly, targeted integration fixes are applied where needed, and the "
            "integration worktree is ready for verification."
        )
    )
    depends_on = ", ".join(execution_step.depends_on) if execution_step and execution_step.depends_on else "none"
    owned_paths = "\n".join(f"- {path}" for path in execution_step.owned_paths) if execution_step and execution_step.owned_paths else "- none declared"
    step_metadata = execution_step.metadata if execution_step and execution_step.metadata else {}
    try:
        return template.format(
            repo_dir=context.paths.repo_dir,
            docs_dir=context.paths.docs_dir,
            workflow_mode=workflow_mode,
            test_command=test_command,
            task_title=task_title,
            display_description=display_description,
            codex_description=codex_description,
            success_criteria=success_criteria,
            depends_on=depends_on,
            owned_paths=owned_paths,
            step_metadata=json.dumps(step_metadata, indent=2, sort_keys=True) if step_metadata else "{}",
            candidate_rationale=candidate.rationale,
            memory_context=memory_context,
            plan_snapshot=compact_text(plan_text, 4000),
            mid_term_plan=compact_text(mid_term, 2500),
            scope_guard=compact_text(scope_guard, 2500),
            research_notes=compact_text(research_notes, 2500),
            research_notes_file=context.paths.research_notes_file,
            failing_command=failing_command,
            failing_summary=compact_text(failing_summary, 1200) or "No merge summary was captured.",
            failing_stdout=compact_text(failing_stdout, 4000) or "No stdout captured.",
            failing_stderr=compact_text(failing_stderr, 4000) or "No stderr captured.",
            merge_targets=", ".join(merge_targets or []) or "none declared",
            extra_prompt=context.runtime.extra_prompt.strip() or "None.",
        )
    except KeyError as exc:
        raise ValueError(f"Unknown placeholder in merger prompt template: {exc.args[0]}") from exc


def finalization_prompt(
    context: ProjectContext,
    plan_state: ExecutionPlanState,
    repo_inputs: dict[str, str],
    template_text: str | None = None,
) -> str:
    workflow_mode = normalize_workflow_mode(getattr(context.runtime, "workflow_mode", "standard"))
    template = template_text or load_finalization_prompt_template(workflow_mode)
    completed_steps = "\n".join(
        [
            f"- {step.step_id}: {step.title} :: {step.success_criteria or 'Completed'}"
            for step in plan_state.steps
            if step.status == "completed"
        ]
    ).strip() or "- No completed steps recorded."
    try:
        return template.format(
            repo_dir=context.paths.repo_dir,
            docs_dir=context.paths.docs_dir,
            workflow_mode=workflow_mode,
            plan_title=plan_state.plan_title.strip() or context.metadata.display_name or context.metadata.slug,
            project_prompt=plan_state.project_prompt.strip() or "No prompt recorded.",
            plan_summary=plan_state.summary.strip() or "No execution summary recorded.",
            test_command=plan_state.default_test_command.strip() or context.runtime.test_cmd,
            completed_steps=completed_steps,
            readme=repo_inputs["readme"],
            agents=repo_inputs["agents"],
            docs=repo_inputs["docs"],
            closeout_report_file=context.paths.closeout_report_file,
            ml_mode_state_file=context.paths.ml_mode_state_file,
            ml_experiment_reports_dir=context.paths.ml_experiment_reports_dir,
            ml_experiment_report_file=context.paths.ml_experiment_report_file,
            ml_experiment_results_svg_file=context.paths.ml_experiment_results_svg_file,
            extra_prompt=context.runtime.extra_prompt.strip() or "None.",
        )
    except KeyError as exc:
        raise ValueError(f"Unknown placeholder in finalization prompt template: {exc.args[0]}") from exc


def optimization_prompt(
    context: ProjectContext,
    plan_state: ExecutionPlanState,
    scan_result: Any,
    template_text: str | None = None,
) -> str:
    template = template_text or load_optimization_prompt_template()
    candidate_files = "\n".join(f"- {path}" for path in getattr(scan_result, "candidate_files", []) or []) or "- No candidate files selected."
    candidates_payload = json.dumps(
        [item.to_dict() for item in getattr(scan_result, "candidates", []) or []],
        indent=2,
        sort_keys=True,
    )
    try:
        return template.format(
            repo_dir=context.paths.repo_dir,
            docs_dir=context.paths.docs_dir,
            plan_title=plan_state.plan_title.strip() or context.metadata.display_name or context.metadata.slug,
            project_prompt=plan_state.project_prompt.strip() or "No prompt recorded.",
            plan_summary=plan_state.summary.strip() or "No execution summary recorded.",
            test_command=plan_state.default_test_command.strip() or context.runtime.test_cmd,
            optimization_mode=getattr(scan_result, "mode", "light"),
            scanned_file_count=int(getattr(scan_result, "scanned_file_count", 0) or 0),
            candidate_files=candidate_files,
            optimization_candidates=candidates_payload,
            extra_prompt=context.runtime.extra_prompt.strip() or "None.",
        )
    except KeyError as exc:
        raise ValueError(f"Unknown placeholder in optimization prompt template: {exc.args[0]}") from exc


def reflection_markdown(task: str, test_summary: str, changed_files: list[str], commit_hashes: list[str]) -> str:
    lines = [
        "# Block Review",
        "",
        f"- Timestamp: {now_utc_iso()}",
        f"- Active task: {task}",
        f"- Changed files: {', '.join(changed_files) if changed_files else 'none'}",
        f"- Commits: {', '.join(commit_hashes) if commit_hashes else 'none'}",
        "",
        "## Verification",
        test_summary,
        "",
        "## Lessons",
        "- Preserve scope and only retain documentation that matches verified implementation.",
        "- Prefer incremental changes that can be rolled back to the last safe revision.",
        "",
    ]
    return "\n".join(lines)


def attempt_history_entry(block_index: int, task: str, outcome: str, commit_hashes: list[str]) -> str:
    lines = [
        f"## Block {block_index}",
        "",
        f"- Timestamp: {now_utc_iso()}",
        f"- Task: {task}",
        f"- Outcome: {outcome}",
        f"- Commits: {', '.join(commit_hashes) if commit_hashes else 'none'}",
        "",
    ]
    return "\n".join(lines)


def build_checkpoint_timeline(plan_text: str, checkpoint_interval_blocks: int) -> list[Checkpoint]:
    items = [item for item in extract_plan_items(plan_text) if not item.text.lower().startswith("do not")]
    if not items:
        return [
            Checkpoint(
                checkpoint_id="CP1",
                title="Initial stabilization checkpoint",
                plan_refs=[],
                target_block=max(1, checkpoint_interval_blocks),
                deadline_at="",
                created_at=now_utc_iso(),
            )
        ]
    checkpoints: list[Checkpoint] = []
    for index, item in enumerate(items, start=1):
        checkpoints.append(
            Checkpoint(
                checkpoint_id=f"CP{index}",
                title=item.text,
                plan_refs=[item.item_id],
                target_block=max(1, index * checkpoint_interval_blocks),
                deadline_at="",
                created_at=now_utc_iso(),
            )
        )
    return checkpoints


def checkpoint_timeline_markdown(checkpoints: list[Checkpoint]) -> str:
    lines = [
        "# Checkpoint Timeline",
        "",
        "This timeline is derived from the saved plan and is intended for user review at checkpoint boundaries.",
        "",
    ]
    for checkpoint in checkpoints:
        refs = ", ".join(checkpoint.plan_refs) if checkpoint.plan_refs else "none"
        lines.extend(
            [
                f"## {checkpoint.checkpoint_id}",
                f"- Title: {checkpoint.title}",
                f"- Target block: {checkpoint.target_block}",
                f"- Deadline: {checkpoint.deadline_at or 'none'}",
                f"- Plan refs: {refs}",
                f"- Status: {checkpoint.status}",
                "",
            ]
        )
    return "\n".join(lines)


def execution_plan_markdown(
    context: ProjectContext,
    plan_title: str,
    project_prompt: str,
    summary: str,
    workflow_mode: str,
    execution_mode: str,
    steps: list[ExecutionStep],
) -> str:
    lines = [
        "# Execution Plan",
        "",
        f"- Repository: {context.metadata.display_name or context.metadata.slug}",
        f"- Working directory: {context.paths.repo_dir}",
        f"- Source: {context.metadata.repo_url}",
        f"- Branch: {context.metadata.branch}",
        f"- Generated at: {now_utc_iso()}",
        "",
        "## Plan Title",
        plan_title.strip() or context.metadata.display_name or context.metadata.slug,
        "",
        "## User Prompt",
        project_prompt.strip() or "No prompt recorded.",
        "",
        "## Execution Summary",
        summary.strip() or "Codex-generated execution plan for the current repository state.",
        "",
        "## Workflow Mode",
        normalize_workflow_mode(workflow_mode),
        "",
        "## Execution Mode",
        _normalize_execution_mode(execution_mode),
        "",
        "## Planned Steps",
    ]
    if not steps:
        lines.append("- ST1: Establish a minimal, testable first step and verify it locally.")
    for step in steps:
        step_kind = str((step.metadata or {}).get("step_kind", "")).strip().lower() or "task"
        step_model = resolve_step_model_choice(step, context.runtime)
        configured_provider = step.model_provider or "auto"
        configured_model = step.model or "auto"
        lines.extend(
            [
                f"- {step.step_id}: {step.title}",
                f"  - UI description: {step.display_description or step.title}",
                f"  - Codex instruction: {step.codex_description or step.display_description or step.title}",
                f"  - Step kind: {step_kind}",
                f"  - Model provider: {configured_provider} -> {step_model.provider} ({step_model.reason})",
                f"  - Model: {configured_model} -> {step_model.model or 'provider default'}",
                f"  - GPT reasoning: {step.reasoning_effort or context.runtime.effort or 'high'}",
                f"  - Parallel group: {step.parallel_group or 'none'}",
                f"  - Depends on: {', '.join(step.depends_on) if step.depends_on else 'none'}",
                f"  - Owned paths: {', '.join(step.owned_paths) if step.owned_paths else 'none declared'}",
                f"  - Verification: {step.test_command or 'Use the default test command.'}",
                f"  - Success criteria: {step.success_criteria or 'Verification command completes successfully.'}",
            ]
        )
        merge_from = (step.metadata or {}).get("merge_from", [])
        if isinstance(merge_from, list) and merge_from:
            lines.append(f"  - Merge from: {', '.join(str(item).strip() for item in merge_from if str(item).strip())}")
        join_policy = str((step.metadata or {}).get("join_policy", "")).strip()
        if join_policy:
            lines.append(f"  - Join policy: {join_policy}")
        if step.metadata:
            lines.append(f"  - Metadata: {json.dumps(step.metadata, ensure_ascii=False, sort_keys=True)}")
    lines.extend(
        [
            "",
            "## Non-Goals",
            "- Do not skip verification for any planned step.",
            "- Do not widen scope beyond the current prompt unless the user updates the plan.",
            "",
            "## Operating Constraints",
            "- Treat each planned step as a checkpoint.",
            "- In parallel mode, only dependency-ready steps with disjoint owned paths may run together.",
            "- Commit and push after a verified step when an origin remote is configured.",
            "- Users may edit only steps that have not started yet.",
            "",
        ]
    )
    return "\n".join(lines)


def execution_steps_to_plan_items(steps: list[ExecutionStep]) -> list[PlanItem]:
    return [PlanItem(item_id=step.step_id, text=step.title) for step in steps if step.title.strip()]


def _execution_graph_levels(steps: list[ExecutionStep]) -> list[list[ExecutionStep]]:
    if not steps:
        return []
    step_ids = [step.step_id for step in steps]
    step_by_id = {step.step_id: step for step in steps}
    visited: set[str] = set()
    levels: list[list[ExecutionStep]] = []
    while len(visited) < len(step_ids):
        ready = [
            step_by_id[step_id]
            for step_id in step_ids
            if step_id not in visited
            and all(dep in visited for dep in step_by_id[step_id].depends_on if dep in step_by_id)
        ]
        if not ready:
            for step_id in step_ids:
                if step_id not in visited:
                    ready = [step_by_id[step_id]]
                    break
        levels.append(ready)
        visited.update(step.step_id for step in ready)
    return levels


def execution_plan_svg(title: str, steps: list[ExecutionStep], execution_mode: str = "parallel") -> str:
    def _orthogonal_path(start_x: float, start_y: float, end_x: float, end_y: float) -> str:
        if abs(start_y - end_y) < 0.01:
            return f"M {start_x} {start_y} H {end_x}"
        middle_x = round(start_x + (end_x - start_x) / 2, 1)
        return f"M {start_x} {start_y} H {middle_x} V {end_y} H {end_x}"

    font_family = "Segoe UI, Malgun Gothic, sans-serif"
    width = 1180
    box_width = 220
    box_height = 136
    gap_x = 32
    gap_y = 36
    margin_x = 40
    margin_y = 56
    per_row = 4
    rows = max(1, (len(steps) + per_row - 1) // per_row)
    height = margin_y * 2 + rows * box_height + max(0, rows - 1) * gap_y + 80
    palette = {
        "completed": ("#0f766e", "#ecfeff"),
        "running": ("#1d4ed8", "#eff6ff"),
        "paused": ("#7c3aed", "#f5f3ff"),
        "failed": ("#b91c1c", "#fef2f2"),
        "pending": ("#cbd5e1", "#0f172a"),
    }
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">',
        '<rect width="100%" height="100%" fill="#f8fafc" />',
        svg_text_element(margin_x, 34, wrap_svg_text(title, 70, max_lines=2), fill="#0f172a", font_size=24, font_family=font_family, font_weight="700", line_height=28),
    ]
    uses_dag = execution_mode.strip().lower() == "parallel" and any(step.depends_on or step.owned_paths for step in steps)
    if uses_dag:
        levels = _execution_graph_levels(steps)
        dag_margin_x = 48
        dag_margin_y = 72
        dag_box_width = 220
        dag_box_height = 136
        dag_gap_x = 120
        dag_gap_y = 30
        split_gap = 44
        merge_gap = 38
        max_rows = max((len(level) for level in levels), default=1)
        dag_width = max(
            width,
            dag_margin_x * 2 + len(levels) * dag_box_width + max(0, len(levels) - 1) * dag_gap_x,
        )
        dag_height = max(
            height,
            dag_margin_y * 2 + max_rows * dag_box_height + max(0, max_rows - 1) * dag_gap_y + 32,
        )
        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{dag_width}" height="{dag_height}" viewBox="0 0 {dag_width} {dag_height}" role="img">',
            '<rect width="100%" height="100%" fill="#f8fafc" />',
            (
                '<defs>'
                '<marker id="flow-arrow" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto" markerUnits="strokeWidth">'
                '<path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8" />'
                "</marker>"
                "</defs>"
            ),
            svg_text_element(dag_margin_x, 34, wrap_svg_text(title, 70, max_lines=2), fill="#0f172a", font_size=24, font_family=font_family, font_weight="700", line_height=28),
        ]
        positions: dict[str, tuple[float, float]] = {}
        for level_index, level in enumerate(levels):
            x = dag_margin_x + level_index * (dag_box_width + dag_gap_x)
            parts.append(
                svg_text_element(x, 56, [f"Layer {level_index + 1}"], fill="#475569", font_size=13, font_family=font_family, font_weight="600")
            )
            for row_index, step in enumerate(level):
                y = dag_margin_y + row_index * (dag_box_height + dag_gap_y)
                positions[step.step_id] = (x, y)
        incoming: dict[str, list[str]] = {step.step_id: [] for step in steps}
        outgoing: dict[str, list[str]] = {step.step_id: [] for step in steps}
        for step in steps:
            for dependency in step.depends_on:
                if dependency not in positions or step.step_id not in positions:
                    continue
                incoming.setdefault(step.step_id, []).append(dependency)
                outgoing.setdefault(dependency, []).append(step.step_id)
        split_points: dict[str, tuple[float, float]] = {}
        merge_points: dict[str, tuple[float, float]] = {}
        for step in steps:
            if step.step_id not in positions:
                continue
            x, y = positions[step.step_id]
            center_y = y + dag_box_height / 2
            if len(outgoing.get(step.step_id, [])) > 1:
                split_points[step.step_id] = (x + dag_box_width + split_gap, center_y)
            if len(incoming.get(step.step_id, [])) > 1:
                merge_points[step.step_id] = (x - merge_gap, center_y)
        for step_id, (junction_x, junction_y) in split_points.items():
            node_x, node_y = positions[step_id]
            parts.append(
                f'<path d="M {node_x + dag_box_width} {node_y + dag_box_height / 2} H {junction_x}" stroke="#94a3b8" stroke-width="3" fill="none" stroke-linecap="round" />'
            )
        for source_step_id, targets in outgoing.items():
            if source_step_id not in positions:
                continue
            source_x, source_y = positions[source_step_id]
            start_x, start_y = split_points.get(
                source_step_id,
                (source_x + dag_box_width, source_y + dag_box_height / 2),
            )
            for target_step_id in targets:
                if target_step_id not in positions:
                    continue
                target_x, target_y = positions[target_step_id]
                end_x, end_y = merge_points.get(
                    target_step_id,
                    (target_x, target_y + dag_box_height / 2),
                )
                marker = ' marker-end="url(#flow-arrow)"' if target_step_id not in merge_points else ""
                parts.append(
                    f'<path d="{_orthogonal_path(start_x, start_y, end_x, end_y)}" stroke="#94a3b8" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"{marker} />'
                )
        for step_id, (junction_x, junction_y) in merge_points.items():
            node_x, _node_y = positions[step_id]
            parts.append(
                f'<path d="M {junction_x} {junction_y} H {node_x}" stroke="#94a3b8" stroke-width="3" fill="none" stroke-linecap="round" marker-end="url(#flow-arrow)" />'
            )
        for junction_x, junction_y in split_points.values():
            parts.append(f'<circle cx="{junction_x}" cy="{junction_y}" r="5" fill="#f8fafc" stroke="#94a3b8" stroke-width="2" />')
        for junction_x, junction_y in merge_points.values():
            parts.append(f'<circle cx="{junction_x}" cy="{junction_y}" r="5" fill="#f8fafc" stroke="#94a3b8" stroke-width="2" />')
        for step in steps:
            if step.step_id not in positions:
                continue
            x, y = positions[step.step_id]
            status = step.status if step.status in palette else "pending"
            fill, text_fill = palette[status]
            title_lines = wrap_svg_text(compact_text(step.title, 90), 24, max_lines=2)
            detail_source = step.display_description or (", ".join(step.depends_on) if step.depends_on else "")
            if not detail_source and step.owned_paths:
                detail_source = f"{len(step.owned_paths)} owned path(s)"
            detail_lines = wrap_svg_text(compact_text(detail_source or "no DAG metadata", 96), 28, max_lines=2)
            parts.extend(
                [
                    f'<rect x="{x}" y="{y}" rx="20" ry="20" width="{dag_box_width}" height="{dag_box_height}" fill="{fill}" />',
                    svg_text_element(x + 18, y + 26, [step.step_id], fill=text_fill, font_size=14, font_family=font_family, font_weight="700"),
                    svg_text_element(x + 18, y + 48, title_lines, fill=text_fill, font_size=13, font_family=font_family, line_height=16),
                    svg_text_element(x + 18, y + 82, detail_lines, fill=text_fill, font_size=11, font_family=font_family, line_height=14),
                    svg_text_element(x + 18, y + 120, [status], fill=text_fill, font_size=11, font_family=font_family),
                ]
            )
        parts.append("</svg>")
        return "\n".join(parts)
    for index, step in enumerate(steps):
        row = index // per_row
        col = index % per_row
        x = margin_x + col * (box_width + gap_x)
        y = margin_y + row * (box_height + gap_y)
        status = step.status if step.status in palette else "pending"
        fill, text_fill = palette[status]
        title_lines = wrap_svg_text(compact_text(step.title, 90), 24, max_lines=2)
        detail_lines = wrap_svg_text(
            compact_text(step.display_description or step.parallel_group or step.test_command or "default verification", 96),
            28,
            max_lines=2,
        )
        parts.extend(
            [
                f'<rect x="{x}" y="{y}" rx="20" ry="20" width="{box_width}" height="{box_height}" fill="{fill}" />',
                svg_text_element(x + 18, y + 28, [step.step_id], fill=text_fill, font_size=14, font_family=font_family, font_weight="700"),
                svg_text_element(x + 18, y + 54, title_lines, fill=text_fill, font_size=13, font_family=font_family, line_height=16),
                svg_text_element(x + 18, y + 88, detail_lines, fill=text_fill, font_size=11, font_family=font_family, line_height=14),
                svg_text_element(x + 18, y + 124, [status], fill=text_fill, font_size=11, font_family=font_family),
            ]
        )
        if col < per_row - 1 and index + 1 < len(steps) and (index + 1) // per_row == row:
            next_x = x + box_width + gap_x
            center_y = y + box_height / 2
            parts.extend(
                [
                    f'<line x1="{x + box_width + 6}" y1="{center_y}" x2="{next_x - 10}" y2="{center_y}" stroke="#94a3b8" stroke-width="4" stroke-linecap="round" />',
                    f'<polygon points="{next_x - 18},{center_y - 8} {next_x - 2},{center_y} {next_x - 18},{center_y + 8}" fill="#94a3b8" />',
                ]
            )
    parts.append("</svg>")
    return "\n".join(parts)
