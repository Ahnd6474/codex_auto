from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from .models import CandidateTask, ProjectContext
from .utils import compact_text, now_utc_iso, read_text, similarity_score, tokenize, write_text


@dataclass(slots=True)
class PlanItem:
    item_id: str
    text: str


def load_template(name: str) -> str:
    return resources.files("codex_auto").joinpath("templates", name).read_text(encoding="utf-8")


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


def generate_long_term_plan(context: ProjectContext, repo_inputs: dict[str, str]) -> str:
    template = load_template("LONG_TERM_PLAN.sample.md")
    repo_name = context.metadata.repo_url.rstrip("/").split("/")[-1].removesuffix(".git")
    seed_goals = _derive_seed_goals(repo_inputs)
    return template.format(
        repo_name=repo_name,
        repo_url=context.metadata.repo_url,
        branch=context.metadata.branch,
        created_at=now_utc_iso(),
        readme_summary=repo_inputs["readme"],
        agents_summary=repo_inputs["agents"],
        docs_summary=repo_inputs["docs"],
        goal_1=seed_goals[0],
        goal_2=seed_goals[1],
        goal_3=seed_goals[2],
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
    template = load_template("SCOPE_GUARD.template.md")
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
            item_id = match.group("id") or f"LT{len(items) + 1}"
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


def build_mid_term_plan(long_term_text: str, limit: int = 5) -> tuple[str, list[PlanItem]]:
    items = extract_plan_items(long_term_text)
    positive_items = [item for item in items if not item.text.lower().startswith("do not")]
    chosen = positive_items[:limit] if positive_items else []
    lines = [
        "# Mid-Term Plan",
        "",
        "This plan is regenerated only at block boundaries and must remain a strict subset of the long-term plan.",
        "",
    ]
    if not chosen:
        lines.append("- [ ] MT1: Establish a verified, low-risk maintenance task based on the current repository state.")
        return "\n".join(lines) + "\n", []
    for index, item in enumerate(chosen, start=1):
        lines.append(f"- [ ] MT{index} -> {item.item_id}: {item.text}")
    lines.append("")
    return "\n".join(lines), chosen


def validate_mid_term_subset(mid_term_text: str, long_term_text: str) -> tuple[bool, list[str]]:
    long_term_ids = {item.item_id for item in extract_plan_items(long_term_text)}
    violations: list[str] = []
    for line in mid_term_text.splitlines():
        match = re.search(r"->\s*([A-Z]{2,}\d+)", line)
        if match and match.group(1) not in long_term_ids:
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
                long_term_refs=[item.item_id],
                score=score,
            )
        )
    if not tasks:
        tasks.append(
            CandidateTask(
                candidate_id="C1",
                title="Stabilize one narrow, testable issue already present in the repository",
                rationale="Fallback task when the long-term plan is not machine-readable.",
                long_term_refs=[],
                score=0.5,
            )
        )
    return tasks


def select_candidate(tasks: list[CandidateTask]) -> CandidateTask:
    return sorted(tasks, key=lambda item: item.score, reverse=True)[0]


def write_active_task(context: ProjectContext, candidate: CandidateTask, memory_context: str) -> None:
    lines = [
        "# Active Task",
        "",
        f"- Selected at: {now_utc_iso()}",
        f"- Candidate: {candidate.candidate_id}",
        f"- Scope refs: {', '.join(candidate.long_term_refs) if candidate.long_term_refs else 'none'}",
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
    use_research: bool = False,
) -> str:
    long_term = read_text(context.paths.long_term_plan_file)
    mid_term = read_text(context.paths.mid_term_plan_file)
    scope_guard = read_text(context.paths.scope_guard_file)
    research_notes = read_text(context.paths.research_notes_file)
    instructions = [
        f"You are working inside the managed repository at {context.paths.repo_dir}.",
        "Follow any AGENTS.md rules in the repository.",
        "Treat docs/LONG_TERM_PLAN.md as immutable unless the user explicitly unlocks it.",
        "Do not expand scope beyond the active task and scope guard.",
        "Prefer small reversible changes with direct tests.",
        "Update README or docs only if they match actual verified behavior.",
        f"Managed planning documents live outside the repo at {context.paths.docs_dir}.",
        f"Pass type: {pass_name}.",
        "",
        "Active task:",
        candidate.title,
        "",
        "Candidate rationale:",
        candidate.rationale,
        "",
        memory_context,
        "",
        "Long-term plan:",
        compact_text(long_term, 4000),
        "",
        "Mid-term plan:",
        compact_text(mid_term, 2500),
        "",
        "Scope guard:",
        compact_text(scope_guard, 2500),
    ]
    if use_research:
        instructions.extend(
            [
                "",
                "Research notes from the previous step or seed context:",
                compact_text(research_notes, 2500),
                "",
                "Use web search only to retrieve directly relevant official documentation, benchmarks, or literature for the current task.",
                f"Write concise findings to {context.paths.research_notes_file} before or alongside implementation.",
            ]
        )
    instructions.extend(
        [
            "",
            "Required output behavior:",
            "- Implement the task directly in code where justified.",
            "- Add or update tests when practical.",
            "- Keep changes traceable and limited.",
            "- If no safe improvement is possible, explain why in docs/BLOCK_REVIEW.md instead of making speculative edits.",
        ]
    )
    return "\n".join(instructions)


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
