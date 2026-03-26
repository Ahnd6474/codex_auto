from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import escape
from pathlib import Path

from .model_selection import normalize_reasoning_effort
from .models import CandidateTask, Checkpoint, ExecutionPlanState, ExecutionStep, ProjectContext
from .utils import compact_text, now_utc_iso, parse_json_text, read_text, similarity_score, tokenize, write_text


@dataclass(slots=True)
class PlanItem:
    item_id: str
    text: str


PLAN_GENERATION_SERIAL_PROMPT_FILENAME = "PLAN_GENERATION_SERIAL_PROMPT.txt"
PLAN_GENERATION_PARALLEL_PROMPT_FILENAME = "PLAN_GENERATION_PARALLEL_PROMPT.txt"
PLAN_GENERATION_PROMPT_FILENAME = PLAN_GENERATION_SERIAL_PROMPT_FILENAME
STEP_EXECUTION_SERIAL_PROMPT_FILENAME = "STEP_EXECUTION_SERIAL_PROMPT.txt"
STEP_EXECUTION_PARALLEL_PROMPT_FILENAME = "STEP_EXECUTION_PARALLEL_PROMPT.txt"
STEP_EXECUTION_PROMPT_FILENAME = STEP_EXECUTION_SERIAL_PROMPT_FILENAME
DEBUGGER_SERIAL_PROMPT_FILENAME = "DEBUGGER_SERIAL_PROMPT.txt"
DEBUGGER_PARALLEL_PROMPT_FILENAME = "DEBUGGER_PARALLEL_PROMPT.txt"
DEBUGGER_PROMPT_FILENAME = DEBUGGER_SERIAL_PROMPT_FILENAME
FINALIZATION_PROMPT_FILENAME = "FINALIZATION_PROMPT.txt"
SCOPE_GUARD_TEMPLATE_FILENAME = "SCOPE_GUARD_TEMPLATE.md"
REFERENCE_GUIDE_FILENAME = "REFERENCE_GUIDE.md"
REFERENCE_GUIDE_DISPLAY_PATH = f"src/jakal_flow/docs/{REFERENCE_GUIDE_FILENAME}"


def source_docs_dir() -> Path:
    return Path(__file__).resolve().parent / "docs"


def source_prompt_template_path(name: str) -> Path:
    return source_docs_dir() / name


def load_source_prompt_template(name: str) -> str:
    return source_prompt_template_path(name).read_text(encoding="utf-8")


def _normalize_execution_mode(value: str | None) -> str:
    return "parallel" if str(value or "").strip().lower() == "parallel" else "serial"


def plan_generation_prompt_filename(execution_mode: str | None) -> str:
    if _normalize_execution_mode(execution_mode) == "parallel":
        return PLAN_GENERATION_PARALLEL_PROMPT_FILENAME
    return PLAN_GENERATION_SERIAL_PROMPT_FILENAME


def step_execution_prompt_filename(execution_mode: str | None) -> str:
    if _normalize_execution_mode(execution_mode) == "parallel":
        return STEP_EXECUTION_PARALLEL_PROMPT_FILENAME
    return STEP_EXECUTION_SERIAL_PROMPT_FILENAME


def load_plan_generation_prompt_template(execution_mode: str | None) -> str:
    return load_source_prompt_template(plan_generation_prompt_filename(execution_mode))


def load_step_execution_prompt_template(execution_mode: str | None) -> str:
    return load_source_prompt_template(step_execution_prompt_filename(execution_mode))


def debugger_prompt_filename(execution_mode: str | None) -> str:
    if _normalize_execution_mode(execution_mode) == "parallel":
        return DEBUGGER_PARALLEL_PROMPT_FILENAME
    return DEBUGGER_SERIAL_PROMPT_FILENAME


def load_debugger_prompt_template(execution_mode: str | None) -> str:
    return load_source_prompt_template(debugger_prompt_filename(execution_mode))


def load_reference_guide_text() -> str:
    text = read_text(source_prompt_template_path(REFERENCE_GUIDE_FILENAME))
    return compact_text(text, 1500) or f"{REFERENCE_GUIDE_DISPLAY_PATH} not found."


def scan_repository_inputs(repo_dir: Path) -> dict[str, str]:
    readme = read_text(repo_dir / "README.md")
    agents = read_text(repo_dir / "AGENTS.md")
    docs_dir = repo_dir / "docs"
    docs_summaries: list[str] = []
    if docs_dir.exists():
        for path in sorted(docs_dir.rglob("*.md"))[:20]:
            docs_summaries.append(f"## {path.relative_to(repo_dir)}\n{compact_text(read_text(path), 600)}")
    return {
        "readme": compact_text(readme, 2000) or "README.md not found.",
        "agents": compact_text(agents, 1500) or "AGENTS.md not found.",
        "docs": "\n\n".join(docs_summaries) if docs_summaries else "No markdown files under repo/docs.",
    }


def assess_repository_maturity(repo_dir: Path, repo_inputs: dict[str, str]) -> tuple[bool, dict[str, int]]:
    score = 0
    details = {"readme": 0, "docs": 0, "source": 0, "tests": 0}
    if "not found" not in repo_inputs["readme"].lower():
        score += 1
        details["readme"] = 1
    if "no markdown files under repo/docs" not in repo_inputs["docs"].lower():
        score += 1
        details["docs"] = 1
    source_matches = list(repo_dir.glob("src")) + list(repo_dir.glob("app")) + list(repo_dir.glob("package.json")) + list(repo_dir.glob("pyproject.toml"))
    if source_matches:
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
            "Prefer a fully runnable prototype over competitive polish.",
            "Add directly necessary setup, integration, validation, cleanup, and supporting implementation work even if the user did not spell out each item.",
            "Do not invent speculative roadmap items or optional expansion beyond the requested prototype scope.",
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
    execution_mode: str = "serial",
    template_text: str | None = None,
) -> str:
    template = template_text or load_plan_generation_prompt_template(execution_mode)
    try:
        return template.format(
            repo_dir=context.paths.repo_dir,
            max_steps=max(3, max_steps),
            execution_mode=execution_mode.strip().lower() or "serial",
            readme=repo_inputs["readme"],
            agents=repo_inputs["agents"],
            reference_notes=load_reference_guide_text(),
            docs=repo_inputs["docs"],
            user_prompt=user_prompt.strip(),
        )
    except KeyError as exc:
        raise ValueError(f"Unknown placeholder in plan generation prompt template: {exc.args[0]}") from exc


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
        steps.append(
            ExecutionStep(
                step_id=str(item.get("step_id", item.get("node_id", ""))).strip() or f"ST{len(steps) + 1}",
                title=title,
                display_description=display_description,
                codex_description=codex_description,
                test_command=str(item.get("test_command", "")).strip() or default_test_command,
                success_criteria=str(item.get("success_criteria", "")).strip(),
                reasoning_effort=reasoning_effort,
                parallel_group=parallel_group,
                depends_on=depends_on,
                owned_paths=owned_paths,
                status="pending",
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
    template = template_text or load_step_execution_prompt_template(getattr(context.runtime, "execution_mode", "serial"))
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
    try:
        return template.format(
            repo_dir=context.paths.repo_dir,
            docs_dir=context.paths.docs_dir,
            pass_name=pass_name,
            test_command=test_command,
            task_title=task_title,
            display_description=display_description,
            codex_description=codex_description,
            success_criteria=success_criteria,
            depends_on=depends_on,
            owned_paths=owned_paths,
            candidate_rationale=candidate.rationale,
            memory_context=memory_context,
            plan_snapshot=compact_text(plan_text, 4000),
            mid_term_plan=compact_text(mid_term, 2500),
            scope_guard=compact_text(scope_guard, 2500),
            research_notes=compact_text(research_notes, 2500),
            research_notes_file=context.paths.research_notes_file,
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
    template = template_text or load_debugger_prompt_template(getattr(context.runtime, "execution_mode", "serial"))
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
    try:
        return template.format(
            repo_dir=context.paths.repo_dir,
            docs_dir=context.paths.docs_dir,
            failing_pass_name=failing_pass_name,
            test_command=test_command,
            task_title=task_title,
            display_description=display_description,
            codex_description=codex_description,
            success_criteria=success_criteria,
            depends_on=depends_on,
            owned_paths=owned_paths,
            candidate_rationale=candidate.rationale,
            memory_context=memory_context,
            plan_snapshot=compact_text(plan_text, 4000),
            mid_term_plan=compact_text(mid_term, 2500),
            scope_guard=compact_text(scope_guard, 2500),
            research_notes=compact_text(research_notes, 2500),
            research_notes_file=context.paths.research_notes_file,
            failing_test_summary=compact_text(failing_test_summary, 1200) or "No verification summary was captured.",
            failing_test_stdout=compact_text(failing_test_stdout, 4000) or "No stdout captured.",
            failing_test_stderr=compact_text(failing_test_stderr, 4000) or "No stderr captured.",
            extra_prompt=context.runtime.extra_prompt.strip() or "None.",
        )
    except KeyError as exc:
        raise ValueError(f"Unknown placeholder in debugger prompt template: {exc.args[0]}") from exc


def finalization_prompt(
    context: ProjectContext,
    plan_state: ExecutionPlanState,
    repo_inputs: dict[str, str],
    template_text: str | None = None,
) -> str:
    template = template_text or load_source_prompt_template(FINALIZATION_PROMPT_FILENAME)
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
            plan_title=plan_state.plan_title.strip() or context.metadata.display_name or context.metadata.slug,
            project_prompt=plan_state.project_prompt.strip() or "No prompt recorded.",
            plan_summary=plan_state.summary.strip() or "No execution summary recorded.",
            test_command=plan_state.default_test_command.strip() or context.runtime.test_cmd,
            completed_steps=completed_steps,
            readme=repo_inputs["readme"],
            agents=repo_inputs["agents"],
            docs=repo_inputs["docs"],
            closeout_report_file=context.paths.closeout_report_file,
            extra_prompt=context.runtime.extra_prompt.strip() or "None.",
        )
    except KeyError as exc:
        raise ValueError(f"Unknown placeholder in finalization prompt template: {exc.args[0]}") from exc


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
        "## Execution Mode",
        execution_mode.strip().lower() or "serial",
        "",
        "## Planned Steps",
    ]
    if not steps:
        lines.append("- ST1: Establish a minimal, testable first step and verify it locally.")
    for step in steps:
        lines.extend(
            [
                f"- {step.step_id}: {step.title}",
                f"  - UI description: {step.display_description or step.title}",
                f"  - Codex instruction: {step.codex_description or step.display_description or step.title}",
                f"  - GPT reasoning: {step.reasoning_effort or context.runtime.effort or 'high'}",
                f"  - Parallel group: {step.parallel_group or 'none'}",
                f"  - Depends on: {', '.join(step.depends_on) if step.depends_on else 'none'}",
                f"  - Owned paths: {', '.join(step.owned_paths) if step.owned_paths else 'none declared'}",
                f"  - Verification: {step.test_command or 'Use the default test command.'}",
                f"  - Success criteria: {step.success_criteria or 'Verification command completes successfully.'}",
            ]
        )
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


def execution_plan_svg(title: str, steps: list[ExecutionStep], execution_mode: str = "serial") -> str:
    width = 1180
    box_width = 220
    box_height = 120
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
        f'<text x="{margin_x}" y="34" fill="#0f172a" font-family="Segoe UI, Malgun Gothic, sans-serif" font-size="24" font-weight="700">{escape(title)}</text>',
    ]
    uses_dag = execution_mode.strip().lower() == "parallel" and any(step.depends_on or step.owned_paths for step in steps)
    if uses_dag:
        levels = _execution_graph_levels(steps)
        dag_margin_x = 48
        dag_margin_y = 68
        dag_box_width = 220
        dag_box_height = 112
        dag_gap_x = 92
        dag_gap_y = 28
        dag_width = max(
            width,
            dag_margin_x * 2 + len(levels) * dag_box_width + max(0, len(levels) - 1) * dag_gap_x,
        )
        dag_height = max(
            height,
            dag_margin_y * 2 + max((len(level) for level in levels), default=1) * dag_box_height + max(0, max((len(level) for level in levels), default=1) - 1) * dag_gap_y + 40,
        )
        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{dag_width}" height="{dag_height}" viewBox="0 0 {dag_width} {dag_height}" role="img">',
            '<rect width="100%" height="100%" fill="#f8fafc" />',
            f'<text x="{dag_margin_x}" y="34" fill="#0f172a" font-family="Segoe UI, Malgun Gothic, sans-serif" font-size="24" font-weight="700">{escape(title)}</text>',
        ]
        positions: dict[str, tuple[float, float]] = {}
        for level_index, level in enumerate(levels):
            x = dag_margin_x + level_index * (dag_box_width + dag_gap_x)
            parts.append(
                f'<text x="{x}" y="56" fill="#475569" font-family="Segoe UI, Malgun Gothic, sans-serif" font-size="13" font-weight="600">Layer {level_index + 1}</text>'
            )
            for row_index, step in enumerate(level):
                y = dag_margin_y + row_index * (dag_box_height + dag_gap_y)
                positions[step.step_id] = (x, y)
        for step in steps:
            if step.step_id not in positions:
                continue
            target_x, target_y = positions[step.step_id]
            for dependency in step.depends_on:
                if dependency not in positions:
                    continue
                source_x, source_y = positions[dependency]
                start_x = source_x + dag_box_width
                start_y = source_y + dag_box_height / 2
                end_x = target_x
                end_y = target_y + dag_box_height / 2
                control_x = start_x + (end_x - start_x) / 2
                parts.extend(
                    [
                        f'<path d="M {start_x} {start_y} C {control_x} {start_y}, {control_x} {end_y}, {end_x - 12} {end_y}" stroke="#94a3b8" stroke-width="3" fill="none" stroke-linecap="round" />',
                        f'<polygon points="{end_x - 20},{end_y - 7} {end_x - 4},{end_y} {end_x - 20},{end_y + 7}" fill="#94a3b8" />',
                    ]
                )
        for step in steps:
            if step.step_id not in positions:
                continue
            x, y = positions[step.step_id]
            status = step.status if step.status in palette else "pending"
            fill, text_fill = palette[status]
            title_text = compact_text(step.title, 70)
            detail_source = step.display_description or (", ".join(step.depends_on) if step.depends_on else "")
            if not detail_source and step.owned_paths:
                detail_source = f"{len(step.owned_paths)} owned path(s)"
            detail_text = compact_text(detail_source or "no DAG metadata", 58)
            parts.extend(
                [
                    f'<rect x="{x}" y="{y}" rx="20" ry="20" width="{dag_box_width}" height="{dag_box_height}" fill="{fill}" />',
                    f'<text x="{x + 18}" y="{y + 26}" fill="{text_fill}" font-family="Segoe UI, Malgun Gothic, sans-serif" font-size="14" font-weight="700">{escape(step.step_id)}</text>',
                    f'<text x="{x + 18}" y="{y + 50}" fill="{text_fill}" font-family="Segoe UI, Malgun Gothic, sans-serif" font-size="13">{escape(title_text)}</text>',
                    f'<text x="{x + 18}" y="{y + 76}" fill="{text_fill}" font-family="Segoe UI, Malgun Gothic, sans-serif" font-size="11">{escape(detail_text)}</text>',
                    f'<text x="{x + 18}" y="{y + 96}" fill="{text_fill}" font-family="Segoe UI, Malgun Gothic, sans-serif" font-size="11">{escape(status)}</text>',
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
        title_text = compact_text(step.title, 70)
        detail_text = compact_text(step.display_description or step.parallel_group or step.test_command or "default verification", 58)
        parts.extend(
            [
                f'<rect x="{x}" y="{y}" rx="20" ry="20" width="{box_width}" height="{box_height}" fill="{fill}" />',
                f'<text x="{x + 18}" y="{y + 28}" fill="{text_fill}" font-family="Segoe UI, Malgun Gothic, sans-serif" font-size="14" font-weight="700">{escape(step.step_id)}</text>',
                f'<text x="{x + 18}" y="{y + 54}" fill="{text_fill}" font-family="Segoe UI, Malgun Gothic, sans-serif" font-size="13">{escape(title_text)}</text>',
                f'<text x="{x + 18}" y="{y + 82}" fill="{text_fill}" font-family="Segoe UI, Malgun Gothic, sans-serif" font-size="11">{escape(detail_text)}</text>',
                f'<text x="{x + 18}" y="{y + 102}" fill="{text_fill}" font-family="Segoe UI, Malgun Gothic, sans-serif" font-size="11">{escape(status)}</text>',
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
