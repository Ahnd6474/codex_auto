from __future__ import annotations

from dataclasses import dataclass
import re

from .models import ExecutionStep, ProjectContext

_WHITESPACE_RE = re.compile(r"\s+")
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_OPTIMIZATION_MODE_RE = re.compile(r"\(([^()]+)\)")


@dataclass(frozen=True, slots=True)
class CommitDescriptor:
    author_name: str
    message: str


def build_initial_commit_descriptor(context: ProjectContext) -> CommitDescriptor:
    project_name = _project_name(context)
    return CommitDescriptor(
        author_name="Jakal-Flow-planner",
        message=f"{project_name} plan generation",
    )


def build_setup_commit_descriptor(context: ProjectContext) -> CommitDescriptor:
    project_name = _project_name(context)
    return CommitDescriptor(
        author_name="Jakal-Flow-setup",
        message=f"{project_name} environment setup",
    )


def build_commit_descriptor(
    context: ProjectContext,
    pass_name: str,
    task_name: str,
    execution_step: ExecutionStep | None = None,
) -> CommitDescriptor:
    normalized_pass = _clean(pass_name).lower()
    project_name = _project_name(context)
    subject = _task_subject(task_name, execution_step, fallback=project_name)
    author_slug = "executor"
    message = subject

    if normalized_pass == "project-closeout-pass":
        author_slug = "closeout"
        message = f"{project_name} closeout"
    elif normalized_pass == "project-optimization-pass":
        author_slug = "optimizer"
        optimization_mode = _optimization_mode(task_name)
        message = f"{project_name} optimization ({optimization_mode})"
    elif "plan" in normalized_pass:
        author_slug = "planner"
        message = f"{project_name} plan generation"
    elif normalized_pass.endswith("-debug"):
        if "merge" in normalized_pass:
            author_slug = "merge-resolver"
            message = f"{subject} conflict resolution"
        else:
            author_slug = _parallel_worker_agent(context, execution_step) or "debugger"
            message = f"{subject} debugging"
    elif normalized_pass.endswith("-merger"):
        author_slug = "merge-resolver"
        message = f"{subject} conflict resolution"
    else:
        author_slug = _parallel_worker_agent(context, execution_step) or "executor"

    return CommitDescriptor(
        author_name=f"Jakal-Flow-{author_slug}",
        message=message,
    )


def _project_name(context: ProjectContext) -> str:
    return _clean(context.metadata.display_name or context.metadata.slug or context.paths.repo_dir.name, fallback="Project")


def _task_subject(task_name: str, execution_step: ExecutionStep | None, fallback: str) -> str:
    parallel_titles = _parallel_step_titles(execution_step)
    if parallel_titles:
        return ", ".join(parallel_titles)
    if execution_step is not None:
        title = _clean(execution_step.title)
        if title:
            return title
    return _clean(task_name, fallback=fallback)


def _parallel_step_titles(execution_step: ExecutionStep | None) -> list[str]:
    if execution_step is None or not isinstance(execution_step.metadata, dict):
        return []
    raw_titles = execution_step.metadata.get("parallel_step_titles")
    if not isinstance(raw_titles, list):
        return []
    titles: list[str] = []
    for item in raw_titles:
        title = _clean(item)
        if title:
            titles.append(title)
    return titles


def _parallel_worker_agent(context: ProjectContext, execution_step: ExecutionStep | None) -> str:
    branch = _clean(context.metadata.branch).lower()
    repo_id = _clean(context.metadata.repo_id)
    if not branch.startswith("jakal-flow-parallel-") and ":" not in repo_id:
        return ""

    step_id = ""
    if execution_step is not None and _clean(execution_step.step_id).upper() != "BATCH":
        step_id = execution_step.step_id
    elif ":" in repo_id:
        step_id = repo_id.rsplit(":", 1)[-1]
    return _slug(step_id, fallback="worker")


def _optimization_mode(task_name: str) -> str:
    match = _OPTIMIZATION_MODE_RE.search(task_name or "")
    if match:
        return _clean(match.group(1), fallback="light")
    return "light"


def _slug(value: str, fallback: str) -> str:
    normalized = _clean(value).lower()
    slug = _SLUG_RE.sub("-", normalized).strip("-")
    return slug[:40] or fallback


def _clean(value: object, fallback: str = "") -> str:
    text = _WHITESPACE_RE.sub(" ", str(value or "")).strip()
    return text or fallback
