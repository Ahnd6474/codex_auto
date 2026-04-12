from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .contract_wave import DEFAULT_SPINE_VERSION, load_spine_state, normalize_execution_step_policy, policy_summary
from .errors import SubprocessTimeoutError
from .model_selection import normalize_reasoning_effort
from .models import CandidateTask, Checkpoint, ExecutionPlanState, ExecutionStep, ProjectContext
from .subprocess_utils import run_subprocess
from .step_models import planning_model_selection_guidance, resolve_step_model_choice
from .utils import compact_text, compact_text_balanced, normalize_workflow_mode, now_utc_iso, parse_json_text, read_json, read_text, similarity_score, svg_text_element, tokenize, wrap_svg_text, write_json_if_changed, write_text


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
REVIEWER_A_PROMPT_FILENAME = "REVIEWER_A_PROMPT.txt"
REVIEWER_B_PROMPT_FILENAME = "REVIEWER_B_PROMPT.txt"
ML_PLAN_GENERATION_PROMPT_FILENAME = "ML_PLAN_GENERATION_PROMPT.txt"
ML_STEP_EXECUTION_PROMPT_FILENAME = "ML_STEP_EXECUTION_PROMPT.txt"
ML_FINALIZATION_PROMPT_FILENAME = "ML_FINALIZATION_PROMPT.txt"
SCOPE_GUARD_TEMPLATE_FILENAME = "SCOPE_GUARD_TEMPLATE.md"
REFERENCE_GUIDE_FILENAME = "REFERENCE_GUIDE.md"
REFERENCE_GUIDE_DISPLAY_PATH = f"src/jakal_flow/docs/{REFERENCE_GUIDE_FILENAME}"
_AGENTS_SUMMARY_CACHE: dict[tuple[str, int], tuple[tuple[int, int, int, int], str]] = {}
_REPO_INPUTS_CACHE_VERSION = 2
_PROMPT_BUNDLE_CACHE_VERSION = 1
_REPO_INPUTS_MEMORY_CACHE: dict[str, tuple[str, dict[str, str], dict[str, Any]]] = {}
_PROMPT_BUNDLE_MEMORY_CACHE: dict[str, tuple[str, dict[str, str]]] = {}


def source_docs_dir() -> Path:
    return Path(__file__).resolve().parent / "docs"


def source_prompt_template_path(name: str) -> Path:
    return source_docs_dir() / name


@lru_cache(maxsize=None)
def load_source_prompt_template(name: str) -> str:
    return read_text(source_prompt_template_path(name))


def _normalize_execution_mode(value: str | None) -> str:
    return "parallel"


def _path_cache_token(path: Path) -> tuple[int, int, int, int]:
    try:
        stat_result = path.stat()
    except OSError:
        return (0, 0, 0, 0)
    return (1, int(stat_result.st_mtime_ns), int(stat_result.st_size), int(stat_result.st_ctime_ns))


def _stable_json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _stable_digest(data: Any) -> str:
    return hashlib.sha1(_stable_json_dumps(data).encode("utf-8")).hexdigest()


def _source_inventory_roots(repo_dir: Path) -> list[Path]:
    return [
        repo_dir / "src",
        repo_dir / "app",
        repo_dir / "lib",
        repo_dir / "desktop" / "src",
    ]


def _sorted_scandir(path: Path) -> list[os.DirEntry[str]]:
    try:
        with os.scandir(path) as entries:
            return sorted(entries, key=lambda entry: entry.name)
    except OSError:
        return []


def _cache_file_key(cache_file: Path | None, fallback: Path) -> str:
    return str((cache_file or fallback).resolve())


def _important_invalidation_dirs(repo_dir: Path) -> list[Path]:
    return [
        repo_dir / "docs",
        *_source_inventory_roots(repo_dir),
        repo_dir / "tests",
    ]


def _important_invalidation_files(repo_dir: Path) -> list[Path]:
    return [
        repo_dir / "pyproject.toml",
        repo_dir / "package.json",
        repo_dir / "package-lock.json",
        repo_dir / "pnpm-lock.yaml",
        repo_dir / "yarn.lock",
        repo_dir / "requirements.txt",
        repo_dir / "requirements-dev.txt",
        repo_dir / "setup.py",
        repo_dir / "setup.cfg",
        repo_dir / "tox.ini",
        repo_dir / "Makefile",
        repo_dir / "Dockerfile",
        repo_dir / "docker-compose.yml",
        repo_dir / "docker-compose.yaml",
    ]


def _git_relative_paths(repo_dir: Path, pathspecs: list[str]) -> list[str] | None:
    if not (repo_dir / ".git").exists():
        return None
    if not pathspecs:
        return []
    command = [
        "git",
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "--",
        *pathspecs,
    ]
    try:
        completed = run_subprocess(
            command,
            cwd=repo_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout_seconds=2.0,
        )
    except (OSError, SubprocessTimeoutError):
        return None
    if completed.returncode != 0:
        return None
    values: list[str] = []
    seen: set[str] = set()
    for line in str(completed.stdout or "").splitlines():
        relative = line.strip().replace("\\", "/")
        if not relative or relative in seen:
            continue
        seen.add(relative)
        values.append(relative)
    return values


def _git_status_signature(repo_dir: Path) -> str:
    if not (repo_dir / ".git").exists():
        return "no-git"
    try:
        completed = run_subprocess(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout_seconds=2.0,
        )
    except (OSError, RuntimeError):
        return "git-status-error"
    if completed.returncode != 0:
        return f"git-status-exit-{completed.returncode}"
    lines = [line.rstrip() for line in str(completed.stdout or "").splitlines() if line.strip()]
    return _stable_digest(lines) if lines else "clean"


def _important_tree_signature(repo_dir: Path, *, max_entries: int = 256) -> dict[str, Any]:
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
    entries: list[tuple[str, tuple[int, int, int, int]]] = []
    truncated = False
    for file_path in _important_invalidation_files(repo_dir):
        if file_path.exists() and file_path.is_file():
            relative = str(file_path.relative_to(repo_dir)).replace("\\", "/")
            entries.append((relative, _path_cache_token(file_path)))
            if len(entries) >= max_entries:
                truncated = True
                break
    for root in _important_invalidation_dirs(repo_dir):
        if truncated:
            break
        if not root.exists():
            continue
        stack = [root]
        while stack and not truncated:
            current = stack.pop()
            child_dirs: list[Path] = []
            for entry in _sorted_scandir(current):
                if len(entries) >= max_entries:
                    truncated = True
                    break
                name = entry.name
                if entry.is_dir(follow_symlinks=False):
                    if name in excluded_parts:
                        continue
                    child_dirs.append(Path(entry.path))
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                relative = str(Path(entry.path).relative_to(repo_dir)).replace("\\", "/")
                entries.append((relative, _path_cache_token(Path(entry.path))))
            stack.extend(reversed(child_dirs))
    return {
        "entries": entries,
        "truncated": truncated,
    }


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


def load_reviewer_a_prompt_template() -> str:
    return load_source_prompt_template(REVIEWER_A_PROMPT_FILENAME)


def load_reviewer_b_prompt_template() -> str:
    return load_source_prompt_template(REVIEWER_B_PROMPT_FILENAME)


@lru_cache(maxsize=1)
def load_reference_guide_text() -> str:
    text = read_text(source_prompt_template_path(REFERENCE_GUIDE_FILENAME))
    return compact_text(text, 2200) or f"{REFERENCE_GUIDE_DISPLAY_PATH} not found."


def _summarize_source_inventory(repo_dir: Path, limit: int = 10) -> str:
    roots = _source_inventory_roots(repo_dir)
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
    truncated = False
    scan_limit = max(limit + 200, limit * 20)
    git_paths = _git_relative_paths(repo_dir, ["src", "app", "lib", "desktop/src"])

    if git_paths:
        for relative in git_paths:
            path = repo_dir / relative.replace("/", os.sep)
            if Path(relative).suffix.lower() not in allowed_suffixes:
                continue
            if any(part in excluded_parts for part in path.parts):
                continue
            if relative in seen:
                continue
            seen.add(relative)
            total += 1
            if len(samples) < limit:
                samples.append(relative)
        if total:
            suffix = "" if total <= limit else f", plus {total - limit} more"
            return (
                "Existing implementation files detected. Prefer extending or editing these paths instead of adding "
                f"scaffold-only skeleton steps unless a genuinely new boundary is required: {', '.join(samples)}{suffix}."
            )

    for root in roots:
        if not root.exists():
            continue
        stack = [root]
        while stack:
            current = stack.pop()
            child_dirs: list[Path] = []
            for entry in _sorted_scandir(current):
                name = entry.name
                if entry.is_dir(follow_symlinks=False):
                    if name in excluded_parts:
                        continue
                    child_dirs.append(Path(entry.path))
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                if Path(name).suffix.lower() not in allowed_suffixes:
                    continue
                relative = str(Path(entry.path).relative_to(repo_dir)).replace("\\", "/")
                if relative in seen:
                    continue
                seen.add(relative)
                total += 1
                if len(samples) < limit:
                    samples.append(relative)
                if total >= scan_limit:
                    truncated = True
                    break
            if truncated:
                break
            stack.extend(reversed(child_dirs))
        if truncated:
            break

    if not total:
        return (
            "No obvious implementation files detected under src/, app/, lib/, or desktop/src. "
            "A narrow skeleton/bootstrap step is acceptable only if it establishes the first real contract, "
            "entrypoint, or module."
        )

    if total <= limit:
        suffix = ""
    elif truncated:
        suffix = ", plus many more"
    else:
        suffix = f", plus {total - limit} more"
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
) -> tuple[str, list[str]]:
    docs_dir = repo_dir / "docs"
    if not docs_dir.exists():
        return "No markdown files under repo/docs.", []
    git_paths = _git_relative_paths(repo_dir, ["docs"])
    doc_paths: list[Path] = []
    if git_paths:
        for relative in git_paths:
            if relative.lower().endswith(".md"):
                doc_paths.append(repo_dir / relative.replace("/", os.sep))
                if len(doc_paths) >= max_files + 1:
                    break
    if not doc_paths:
        stack = [docs_dir]
        while stack and len(doc_paths) < max_files + 1:
            current = stack.pop()
            child_dirs: list[Path] = []
            for entry in _sorted_scandir(current):
                if entry.is_dir(follow_symlinks=False):
                    child_dirs.append(Path(entry.path))
                    continue
                if entry.is_file(follow_symlinks=False) and entry.name.lower().endswith(".md"):
                    doc_paths.append(Path(entry.path))
                    if len(doc_paths) >= max_files + 1:
                        break
            stack.extend(reversed(child_dirs))
    if not doc_paths:
        return "No markdown files under repo/docs.", []

    entries: list[str] = []
    sampled_docs: list[str] = []
    current_chars = 0
    for path in doc_paths[:max_files]:
        if len(entries) >= max_files or current_chars >= max_total_chars:
            break
        relative = str(path.relative_to(repo_dir)).replace("\\", "/")
        entry = f"## {relative}\n{compact_text(read_text(path), max_chars_per_file)}"
        if entries and current_chars + len(entry) + 2 > max_total_chars:
            break
        entries.append(entry)
        current_chars += len(entry) + 2
        sampled_docs.append(relative)

    if not entries:
        first_path = doc_paths[0]
        relative = str(first_path.relative_to(repo_dir)).replace("\\", "/")
        entries.append(f"## {relative}\n{compact_text(read_text(first_path), max_chars_per_file)}")
        sampled_docs = [relative]

    if len(doc_paths) > len(entries):
        entries.append("... additional markdown doc files omitted to keep planning context compact.")
    return "\n\n".join(entries), sampled_docs


def _repository_inputs_cache_signature(repo_dir: Path, *, sampled_docs: list[str]) -> dict[str, Any]:
    return {
        "repo_dir": str(repo_dir.resolve()),
        "readme": _path_cache_token(repo_dir / "README.md"),
        "agents": _path_cache_token(repo_dir / "AGENTS.md"),
        "git_status": _git_status_signature(repo_dir),
        "docs_root": _path_cache_token(repo_dir / "docs"),
        "source_roots": {
            str(root.relative_to(repo_dir)).replace("\\", "/"): _path_cache_token(root)
            for root in _source_inventory_roots(repo_dir)
        },
        "sampled_docs": {
            relative: _path_cache_token(repo_dir / relative.replace("/", os.sep))
            for relative in sampled_docs
        },
        "important_tree": _important_tree_signature(repo_dir),
    }


def _build_repository_inputs(repo_dir: Path) -> tuple[dict[str, str], dict[str, Any]]:
    docs_summary, sampled_docs = _summarize_docs_inventory(repo_dir)
    return (
        {
            "readme": compact_text(read_text(repo_dir / "README.md"), 2000) or "README.md not found.",
            "agents": repository_agents_summary(repo_dir),
            "docs": docs_summary,
            "source": _summarize_source_inventory(repo_dir),
        },
        {"sampled_docs": sampled_docs},
    )


def scan_repository_inputs(repo_dir: Path, *, cache_file: Path | None = None, force_refresh: bool = False) -> dict[str, str]:
    cache_key = _cache_file_key(cache_file, repo_dir)
    if not force_refresh:
        cached_memory = _REPO_INPUTS_MEMORY_CACHE.get(cache_key)
        if cached_memory is not None:
            cached_signature, cached_payload, cached_metadata = cached_memory
            sampled_docs = [str(item).strip() for item in cached_metadata.get("sampled_docs", []) if str(item).strip()]
            current_signature = _stable_digest(_repository_inputs_cache_signature(repo_dir, sampled_docs=sampled_docs))
            if current_signature == cached_signature:
                return dict(cached_payload)
        if cache_file:
            cached = read_json(cache_file, default=None)
            if isinstance(cached, dict) and int(cached.get("version", 0) or 0) == _REPO_INPUTS_CACHE_VERSION:
                payload = cached.get("payload")
                metadata = cached.get("metadata")
                if isinstance(payload, dict) and isinstance(metadata, dict):
                    sampled_docs = [str(item).strip() for item in metadata.get("sampled_docs", []) if str(item).strip()]
                    signature = _repository_inputs_cache_signature(repo_dir, sampled_docs=sampled_docs)
                    signature_digest = _stable_digest(signature)
                    if str(cached.get("signature", "")).strip() == signature_digest:
                        normalized_payload = {
                            "readme": str(payload.get("readme", "")).strip() or "README.md not found.",
                            "agents": str(payload.get("agents", "")).strip() or "AGENTS.md not found.",
                            "docs": str(payload.get("docs", "")).strip() or "No markdown files under repo/docs.",
                            "source": str(payload.get("source", "")).strip() or "Source inventory unavailable.",
                        }
                        normalized_metadata = {"sampled_docs": sampled_docs}
                        _REPO_INPUTS_MEMORY_CACHE[cache_key] = (signature_digest, normalized_payload, normalized_metadata)
                        return dict(normalized_payload)

    payload, metadata = _build_repository_inputs(repo_dir)
    signature = _repository_inputs_cache_signature(repo_dir, sampled_docs=list(metadata.get("sampled_docs", [])))
    signature_digest = _stable_digest(signature)
    normalized_metadata = {"sampled_docs": list(metadata.get("sampled_docs", []))}
    _REPO_INPUTS_MEMORY_CACHE[cache_key] = (signature_digest, dict(payload), normalized_metadata)
    if cache_file:
        write_json_if_changed(
            cache_file,
            {
                "version": _REPO_INPUTS_CACHE_VERSION,
                "signature": signature_digest,
                "metadata": normalized_metadata,
                "payload": payload,
            },
        )
    return payload


def repository_agents_summary(repo_dir: Path, *, max_chars: int = 1500) -> str:
    agents_path = repo_dir / "AGENTS.md"
    cache_key = (str(repo_dir.resolve()), max_chars)
    cache_token = _path_cache_token(agents_path)
    cached = _AGENTS_SUMMARY_CACHE.get(cache_key)
    if cached is not None and cached[0] == cache_token:
        return cached[1]
    agents = read_text(agents_path)
    summary = compact_text(agents, max_chars) or "AGENTS.md not found."
    _AGENTS_SUMMARY_CACHE[cache_key] = (cache_token, summary)
    return summary


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


def _planning_prompt_bundle_signature(context: ProjectContext, repo_inputs: dict[str, str]) -> dict[str, Any]:
    runtime = getattr(context, "runtime", None)
    spine_file = getattr(context.paths, "spine_file", context.paths.repo_dir / ".spine")
    shared_contracts_file = getattr(context.paths, "shared_contracts_file", context.paths.repo_dir / ".shared_contracts")
    return {
        "repo_dir": str(context.paths.repo_dir.resolve()),
        "repo_inputs": _stable_digest(repo_inputs),
        "spine": _path_cache_token(spine_file),
        "shared_contracts": _path_cache_token(shared_contracts_file),
        "workflow_mode": normalize_workflow_mode(getattr(runtime, "workflow_mode", "standard")),
    }


def _planning_prompt_bundle(context: ProjectContext, repo_inputs: dict[str, str]) -> dict[str, str]:
    cache_file = getattr(context.paths, "planning_prompt_cache_file", None)
    cache_key = _cache_file_key(cache_file, context.paths.repo_dir / ".planning_prompt_cache")
    signature_digest = _stable_digest(_planning_prompt_bundle_signature(context, repo_inputs))
    cached_memory = _PROMPT_BUNDLE_MEMORY_CACHE.get(cache_key)
    if cached_memory is not None and cached_memory[0] == signature_digest:
        return dict(cached_memory[1])
    if cache_file:
        cached = read_json(cache_file, default=None)
        if (
            isinstance(cached, dict)
            and int(cached.get("version", 0) or 0) == _PROMPT_BUNDLE_CACHE_VERSION
            and str(cached.get("signature", "")).strip() == signature_digest
            and isinstance(cached.get("payload"), dict)
        ):
            payload = {
                "readme": str(cached["payload"].get("readme", "")).strip() or "README.md not found.",
                "agents": str(cached["payload"].get("agents", "")).strip() or "AGENTS.md not found.",
                "docs": str(cached["payload"].get("docs", "")).strip() or "No markdown files under repo/docs.",
                "source": str(cached["payload"].get("source", "")).strip() or "Source inventory unavailable.",
                "spine_version": str(cached["payload"].get("spine_version", "")).strip() or DEFAULT_SPINE_VERSION,
                "shared_contracts_snapshot": (
                    str(cached["payload"].get("shared_contracts_snapshot", "")).strip()
                    or "# Shared Contracts\n\nNo shared contracts recorded yet.\n"
                ),
            }
            _PROMPT_BUNDLE_MEMORY_CACHE[cache_key] = (signature_digest, dict(payload))
            return payload
    payload = {
        **followup_planning_repository_inputs(repo_inputs),
        "spine_version": _planning_spine_version(context),
        "shared_contracts_snapshot": _planning_shared_contracts_snapshot(context),
    }
    _PROMPT_BUNDLE_MEMORY_CACHE[cache_key] = (signature_digest, dict(payload))
    if cache_file:
        write_json_if_changed(
            cache_file,
            {
                "version": _PROMPT_BUNDLE_CACHE_VERSION,
                "signature": signature_digest,
                "payload": payload,
            },
        )
    return payload


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


def _prompt_string_list(values: object) -> list[str]:
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


def _planning_spine_version(context: ProjectContext) -> str:
    spine_file = getattr(getattr(context, "paths", None), "spine_file", None)
    if isinstance(spine_file, Path):
        return load_spine_state(spine_file).current_version or DEFAULT_SPINE_VERSION
    return DEFAULT_SPINE_VERSION


def _planning_shared_contracts_snapshot(context: ProjectContext, *, max_chars: int = 2200) -> str:
    shared_contracts_file = getattr(getattr(context, "paths", None), "shared_contracts_file", None)
    if not isinstance(shared_contracts_file, Path):
        return "# Shared Contracts\n\nNo shared contracts recorded yet.\n"
    return compact_text(
        read_text(shared_contracts_file),
        max_chars,
    ) or "# Shared Contracts\n\nNo shared contracts recorded yet.\n"


def build_fast_planner_outline(
    repo_inputs: dict[str, str],
    user_prompt: str,
    *,
    current_spine_version: str = DEFAULT_SPINE_VERSION,
) -> str:
    source_summary = repo_inputs.get("source", "")
    candidate_owned_paths = _candidate_owned_paths_from_source_summary(source_summary)
    prompt_summary = compact_text(user_prompt.strip(), 180) or "Implement the requested repository change safely."
    payload = {
        "title": compact_text(prompt_summary, 80) or "Compact planning outline",
        "strategy_summary": (
            "Compact planning mode: skip the separate decomposition pass, keep the DAG narrow, and prefer direct edits "
            "to existing implementation surfaces before introducing new scaffolding."
        ),
        "shared_contracts": [],
        "skeleton_step": {
            "block_id": "SK1",
            "needed": False,
            "task_title": "",
            "purpose": "",
            "contract_docstring": "",
            "step_type_hint": "contract",
            "scope_class_hint": "shared_reviewed",
            "verification_profile_hint": "",
            "spine_version_hint": current_spine_version,
            "shared_contracts": [],
            "candidate_owned_paths": [],
            "primary_scope_candidates": [],
            "shared_reviewed_candidates": [],
            "forbidden_core_candidates": [],
            "success_criteria": "",
        },
        "candidate_blocks": [
            {
                "block_id": "B1",
                "goal": prompt_summary,
                "step_type_hint": "feature",
                "scope_class_hint": "free_owned",
                "verification_profile_hint": "",
                "spine_version_hint": current_spine_version,
                "shared_contracts": [],
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
                "primary_scope_candidates": list(candidate_owned_paths),
                "shared_reviewed_candidates": [],
                "forbidden_core_candidates": [],
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


def build_direct_execution_plan(
    project_prompt: str,
    *,
    test_command: str,
    reasoning_effort: str,
    spine_version: str = DEFAULT_SPINE_VERSION,
    step_type: str = "feature",
    direct_execution_score: int = 0,
    direct_execution_reasons: list[str] | None = None,
) -> tuple[str, str, list[ExecutionStep], str]:
    normalized_prompt = " ".join(str(project_prompt or "").split()).strip() or "Implement the requested repository change safely."
    compact_title = compact_text(normalized_prompt, 72) or "Direct execution task"
    is_debug = step_type == "debug"
    display_description = (
        "Diagnose and repair the targeted issue with the smallest safe verified change."
        if is_debug
        else "Handle the small targeted request directly without a multi-step planning pass."
    )
    codex_description = (
        f"Inspect the relevant implementation and verification surfaces for this request first: {normalized_prompt} "
        "Then make the smallest safe code change that resolves the issue, add or update executable verification when practical, "
        "and leave the repository in a passing state."
        if is_debug
        else f"Inspect the relevant implementation files for this request first: {normalized_prompt} "
        "Then make the smallest safe change that satisfies it, add or update executable verification when practical, "
        "and leave the repository in a passing state."
    )
    success_criteria = (
        f"The targeted issue described by the user is resolved and the verification command `{test_command}` exits successfully."
        if is_debug
        else f"The requested small change is implemented and the verification command `{test_command}` exits successfully."
    )
    title = compact_title if len(compact_title) <= 60 else compact_text(compact_title, 60)
    summary = (
        "Direct execution mode was selected because the request looks narrow enough to handle safely in one focused pass "
        "without a separate multi-step plan."
    )
    steps = [
        ExecutionStep(
            step_id="ST1",
            title=title,
            display_description=display_description,
            codex_description=codex_description,
            test_command=test_command,
            success_criteria=success_criteria,
            reasoning_effort=reasoning_effort,
            step_type=step_type,
            scope_class="free_owned",
            spine_version=spine_version,
            verification_profile="",
            metadata={
                "step_kind": "task",
                "direct_execution": True,
                "direct_execution_reason": "small_task_bypass",
                "direct_execution_score": max(0, int(direct_execution_score or 0)),
                "direct_execution_reasons": list(direct_execution_reasons or []),
            },
        )
    ]
    outline = json.dumps(
        {
            "title": title,
            "strategy_summary": "Direct execution bypass: skip planner agents for a narrow request and run one focused block.",
            "shared_contracts": [],
            "skeleton_step": {
                "block_id": "SK1",
                "needed": False,
                "task_title": "",
                "purpose": "",
                "contract_docstring": "",
                "step_type_hint": "contract",
                "scope_class_hint": "shared_reviewed",
                "verification_profile_hint": "",
                "spine_version_hint": spine_version,
                "shared_contracts": [],
                "candidate_owned_paths": [],
                "primary_scope_candidates": [],
                "shared_reviewed_candidates": [],
                "forbidden_core_candidates": [],
                "success_criteria": "",
            },
            "candidate_blocks": [
                {
                    "block_id": "B1",
                    "goal": normalized_prompt,
                    "step_type_hint": step_type,
                    "scope_class_hint": "free_owned",
                    "verification_profile_hint": "",
                    "spine_version_hint": spine_version,
                    "shared_contracts": [],
                    "work_items": [normalized_prompt],
                    "implementation_notes": "Skip separate planner passes and handle the request in one focused execution block.",
                    "testable_boundary": success_criteria,
                    "candidate_owned_paths": [],
                    "primary_scope_candidates": [],
                    "shared_reviewed_candidates": [],
                    "forbidden_core_candidates": [],
                    "parallelizable_after": [],
                    "parallel_notes": "This request is intentionally handled as a single direct block.",
                }
            ],
            "packing_notes": [
                "Use direct execution only for narrow requests that can be completed safely in one pass.",
            ],
        },
        indent=2,
        sort_keys=True,
    )
    return title, summary, steps, outline


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
            continue
        match = re.match(r"#{1,6}\s+(?P<id>[A-Z]{2,}\d+)\s*[-:]\s+(?P<body>.+)", stripped)
        if match and len(tokenize(match.group("body"))) >= 3:
            item_id = match.group("id")
            items.append(PlanItem(item_id=item_id, text=match.group("body").strip()))
            continue
        match = re.match(r"#{1,6}\s+(?P<id>[A-Z]{2,}\d+)\.\s+(?P<body>.+)", stripped)
        if match and len(tokenize(match.group("body"))) >= 2:
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
    prompt_bundle = _planning_prompt_bundle(context, repo_inputs)
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
            f"README:\n{prompt_bundle['readme']}",
            "",
            f"AGENTS:\n{prompt_bundle['agents']}",
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
            f"Docs:\n{prompt_bundle['docs']}",
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
    prompt_bundle = _planning_prompt_bundle(context, repo_inputs)
    try:
        return template.format(
            repo_dir=context.paths.repo_dir,
            max_steps=max(1, max_steps),
            workflow_mode=workflow_mode,
            execution_mode=_normalize_execution_mode(execution_mode),
            readme=prompt_bundle["readme"],
            agents=prompt_bundle["agents"],
            reference_notes=load_reference_guide_text(),
            docs=prompt_bundle["docs"],
            source=prompt_bundle["source"],
            user_prompt=user_prompt.strip(),
            planner_outline=compact_text_balanced(planner_outline.strip(), 4000) or "Planner Agent A output unavailable.",
            model_selection_guidance=planning_model_selection_guidance(runtime),
            current_spine_version=prompt_bundle["spine_version"],
            shared_contracts_snapshot=prompt_bundle["shared_contracts_snapshot"],
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
    prompt_bundle = _planning_prompt_bundle(context, repo_inputs)
    try:
        return template.format(
            repo_dir=context.paths.repo_dir,
            max_steps=max(1, max_steps),
            workflow_mode=workflow_mode,
            execution_mode=_normalize_execution_mode(execution_mode),
            readme=prompt_bundle["readme"],
            agents=prompt_bundle["agents"],
            reference_notes=load_reference_guide_text(),
            docs=prompt_bundle["docs"],
            source=prompt_bundle["source"],
            user_prompt=user_prompt.strip(),
            current_spine_version=prompt_bundle["spine_version"],
            shared_contracts_snapshot=prompt_bundle["shared_contracts_snapshot"],
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
        depends_on = _prompt_string_list(item.get("depends_on", []))
        owned_paths = _prompt_string_list(item.get("owned_paths", []))
        metadata = item.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        else:
            metadata = dict(metadata)
        normalized_metadata_kind = str(metadata.get("step_kind", "")).strip().lower()
        if normalized_metadata_kind == "join" and len(depends_on) < 2:
            metadata.pop("step_kind", None)
            metadata.pop("merge_from", None)
            metadata.pop("join_policy", None)
            metadata.pop("join_reason", None)
        step = ExecutionStep(
            step_id=str(item.get("step_id", item.get("node_id", ""))).strip() or f"ST{len(steps) + 1}",
            title=title,
            display_description=display_description,
            codex_description=codex_description,
            model_provider=str(item.get("model_provider", "")).strip().lower(),
            model=str(item.get("model", item.get("model_slug_input", ""))).strip().lower(),
            test_command=str(item.get("test_command", "")).strip() or default_test_command,
            success_criteria=str(item.get("success_criteria", "")).strip(),
            step_type=str(item.get("step_type", metadata.get("step_type", ""))).strip().lower(),
            scope_class=str(item.get("scope_class", metadata.get("scope_class", ""))).strip().lower(),
            spine_version=str(item.get("spine_version", metadata.get("spine_version", ""))).strip(),
            shared_contracts=_prompt_string_list(item.get("shared_contracts", metadata.get("shared_contracts", []))),
            verification_profile=str(item.get("verification_profile", metadata.get("verification_profile", ""))).strip().lower(),
            promotion_class=str(item.get("promotion_class", metadata.get("promotion_class", ""))).strip().lower(),
            primary_scope_paths=_prompt_string_list(item.get("primary_scope_paths", metadata.get("primary_scope_paths", []))),
            shared_reviewed_paths=_prompt_string_list(item.get("shared_reviewed_paths", metadata.get("shared_reviewed_paths", []))),
            forbidden_core_paths=_prompt_string_list(item.get("forbidden_core_paths", metadata.get("forbidden_core_paths", []))),
            reasoning_effort=reasoning_effort,
            parallel_group=parallel_group,
            depends_on=depends_on,
            owned_paths=owned_paths,
            status="pending",
            metadata=metadata,
        )
        steps.append(normalize_execution_step_policy(step))
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
    if execution_step:
        normalize_execution_step_policy(execution_step)
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
    owned_path_lines = []
    if execution_step and execution_step.owned_paths:
        owned_path_lines.extend(f"- owned: {path}" for path in execution_step.owned_paths)
    if execution_step and execution_step.shared_reviewed_paths:
        owned_path_lines.extend(f"- shared-reviewed: {path}" for path in execution_step.shared_reviewed_paths)
    if execution_step and execution_step.forbidden_core_paths:
        owned_path_lines.extend(f"- forbidden-core: {path}" for path in execution_step.forbidden_core_paths)
    owned_paths = "\n".join(owned_path_lines) if owned_path_lines else "- none declared"
    step_metadata = execution_step.metadata if execution_step and execution_step.metadata else {}
    step_policy = policy_summary(execution_step) if execution_step else "step_type=feature; scope_class=free_owned"
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
            step_metadata=json.dumps({**step_metadata, "policy_summary": step_policy}, indent=2, sort_keys=True) if step_metadata or step_policy else "{}",
            candidate_rationale=candidate.rationale,
            memory_context=memory_context,
            plan_snapshot=compact_text_balanced(plan_text, 4000),
            mid_term_plan=compact_text_balanced(mid_term, 2500),
            scope_guard=compact_text_balanced(scope_guard, 2500),
            research_notes=compact_text_balanced(research_notes, 2500),
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
    if execution_step:
        normalize_execution_step_policy(execution_step)
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
    owned_path_lines = []
    if execution_step and execution_step.owned_paths:
        owned_path_lines.extend(f"- owned: {path}" for path in execution_step.owned_paths)
    if execution_step and execution_step.shared_reviewed_paths:
        owned_path_lines.extend(f"- shared-reviewed: {path}" for path in execution_step.shared_reviewed_paths)
    if execution_step and execution_step.forbidden_core_paths:
        owned_path_lines.extend(f"- forbidden-core: {path}" for path in execution_step.forbidden_core_paths)
    owned_paths = "\n".join(owned_path_lines) if owned_path_lines else "- none declared"
    step_metadata = execution_step.metadata if execution_step and execution_step.metadata else {}
    step_policy = policy_summary(execution_step) if execution_step else "step_type=debug; scope_class=free_owned"
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
            step_metadata=json.dumps({**step_metadata, "policy_summary": step_policy}, indent=2, sort_keys=True) if step_metadata or step_policy else "{}",
            candidate_rationale=candidate.rationale,
            memory_context=memory_context,
            plan_snapshot=compact_text_balanced(plan_text, 4000),
            mid_term_plan=compact_text_balanced(mid_term, 2500),
            scope_guard=compact_text_balanced(scope_guard, 2500),
            research_notes=compact_text_balanced(research_notes, 2500),
            research_notes_file=context.paths.research_notes_file,
            ml_step_report_file=context.paths.ml_step_report_file,
            failing_test_summary=compact_text_balanced(failing_test_summary, 1200) or "No verification summary was captured.",
            failing_test_stdout=compact_text_balanced(failing_test_stdout, 4000) or "No stdout captured.",
            failing_test_stderr=compact_text_balanced(failing_test_stderr, 4000) or "No stderr captured.",
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
    if execution_step:
        normalize_execution_step_policy(execution_step)
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
    owned_path_lines = []
    if execution_step and execution_step.owned_paths:
        owned_path_lines.extend(f"- owned: {path}" for path in execution_step.owned_paths)
    if execution_step and execution_step.shared_reviewed_paths:
        owned_path_lines.extend(f"- shared-reviewed: {path}" for path in execution_step.shared_reviewed_paths)
    if execution_step and execution_step.forbidden_core_paths:
        owned_path_lines.extend(f"- forbidden-core: {path}" for path in execution_step.forbidden_core_paths)
    owned_paths = "\n".join(owned_path_lines) if owned_path_lines else "- none declared"
    step_metadata = execution_step.metadata if execution_step and execution_step.metadata else {}
    step_policy = policy_summary(execution_step) if execution_step else "step_type=integration; scope_class=shared_reviewed"
    agents_summary = repository_agents_summary(context.paths.repo_dir, max_chars=1200)
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
            agents_summary=agents_summary,
            step_metadata=json.dumps({**step_metadata, "policy_summary": step_policy}, indent=2, sort_keys=True) if step_metadata or step_policy else "{}",
            candidate_rationale=candidate.rationale,
            memory_context=memory_context,
            plan_snapshot=compact_text_balanced(plan_text, 4000),
            mid_term_plan=compact_text_balanced(mid_term, 2500),
            scope_guard=compact_text_balanced(scope_guard, 2500),
            research_notes=compact_text_balanced(research_notes, 2500),
            research_notes_file=context.paths.research_notes_file,
            failing_command=failing_command,
            failing_summary=compact_text_balanced(failing_summary, 1200) or "No merge summary was captured.",
            failing_stdout=compact_text_balanced(failing_stdout, 4000) or "No stdout captured.",
            failing_stderr=compact_text_balanced(failing_stderr, 4000) or "No stderr captured.",
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


def _execution_steps_outline(plan_state: ExecutionPlanState) -> str:
    return "\n".join(
        f"- {step.step_id}: {step.title} :: {step.success_criteria or 'No explicit success criteria recorded.'}"
        for step in plan_state.steps
    ).strip() or "- No execution steps recorded."


def reviewer_a_prompt(
    context: ProjectContext,
    plan_state: ExecutionPlanState,
    repo_inputs: dict[str, str],
    template_text: str | None = None,
) -> str:
    workflow_mode = normalize_workflow_mode(getattr(context.runtime, "workflow_mode", "standard"))
    template = template_text or load_reviewer_a_prompt_template()
    try:
        return template.format(
            repo_dir=context.paths.repo_dir,
            docs_dir=context.paths.docs_dir,
            workflow_mode=workflow_mode,
            test_command=plan_state.default_test_command.strip() or context.runtime.test_cmd,
            plan_title=plan_state.plan_title.strip() or context.metadata.display_name or context.metadata.slug,
            project_prompt=plan_state.project_prompt.strip() or "No prompt recorded.",
            plan_summary=plan_state.summary.strip() or "No execution summary recorded.",
            execution_steps=_execution_steps_outline(plan_state),
            readme=repo_inputs["readme"],
            agents=repo_inputs["agents"],
            docs=repo_inputs["docs"],
            requirements_matrix_file=context.paths.requirements_matrix_file,
            global_test_plan_file=context.paths.global_test_plan_file,
            test_strength_report_file=context.paths.test_strength_report_file,
            reviewer_a_verdict_file=context.paths.reviewer_a_verdict_file,
            extra_prompt=context.runtime.extra_prompt.strip() or "None.",
        )
    except KeyError as exc:
        raise ValueError(f"Unknown placeholder in reviewer A prompt template: {exc.args[0]}") from exc


def reviewer_b_prompt(
    context: ProjectContext,
    plan_state: ExecutionPlanState,
    template_text: str | None = None,
) -> str:
    workflow_mode = normalize_workflow_mode(getattr(context.runtime, "workflow_mode", "standard"))
    template = template_text or load_reviewer_b_prompt_template()
    reviewer_a_verdict_payload = read_json(context.paths.reviewer_a_verdict_file, default=None)
    reviewer_a_verdict_text = (
        json.dumps(reviewer_a_verdict_payload, ensure_ascii=False, indent=2, sort_keys=True)
        if reviewer_a_verdict_payload is not None
        else "Reviewer A verdict file is missing."
    )
    try:
        return template.format(
            repo_dir=context.paths.repo_dir,
            docs_dir=context.paths.docs_dir,
            workflow_mode=workflow_mode,
            plan_title=plan_state.plan_title.strip() or context.metadata.display_name or context.metadata.slug,
            project_prompt=plan_state.project_prompt.strip() or "No prompt recorded.",
            plan_summary=plan_state.summary.strip() or "No execution summary recorded.",
            execution_steps=_execution_steps_outline(plan_state),
            reviewer_a_verdict=reviewer_a_verdict_text,
            requirements_matrix_file=context.paths.requirements_matrix_file,
            global_test_plan_file=context.paths.global_test_plan_file,
            test_strength_report_file=context.paths.test_strength_report_file,
            reviewer_a_verdict_file=context.paths.reviewer_a_verdict_file,
            reviewer_b_decision_file=context.paths.reviewer_b_decision_file,
            replan_packet_file=context.paths.replan_packet_file,
            closeout_report_file=context.paths.closeout_report_file,
            pass_log_file=context.paths.pass_log_file,
            block_log_file=context.paths.block_log_file,
            extra_prompt=context.runtime.extra_prompt.strip() or "None.",
        )
    except KeyError as exc:
        raise ValueError(f"Unknown placeholder in reviewer B prompt template: {exc.args[0]}") from exc


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
            optimization_mode=getattr(scan_result, "mode", "off"),
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


def _flow_status_to_palette(status: str) -> str:
    normalized = str(status).strip().lower()
    mapping = {
        "done": "completed",
        "succeeded": "completed",
        "success": "completed",
        "in_progress": "running",
        "running": "running",
        "started": "running",
        "integrating": "running",
        "awaiting_review": "paused",
        "paused_for_approval": "paused",
        "blocked": "paused",
        "failed": "failed",
        "error": "failed",
        "rolled_back": "failed",
        "rolled_back_to_safe_revision": "failed",
        "lineage_rolled_back_to_safe_revision": "failed",
        "not_started": "pending",
        "queued": "pending",
    }
    if normalized in {"completed", "running", "paused", "failed", "pending"}:
        return normalized
    return mapping.get(normalized, "pending")


def _checkpoint_status_text(status: str | None) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"", "not_started", "queued"}:
        return "pending"
    return normalized


def _positive_int(value: Any, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _latest_block_for_lineage(blocks: list[dict[str, Any]], lineage_id: str) -> dict[str, Any] | None:
    lineage_key = str(lineage_id).strip()
    if not lineage_key:
        return None
    for block in reversed(blocks):
        if not isinstance(block, dict):
            continue
        if str(block.get("lineage_id", "")).strip() == lineage_key:
            return block
    return None


def _latest_checkpoint_block(
    block_entries: list[dict[str, Any]],
    target_block: int,
    lineage_id: str,
) -> dict[str, Any] | None:
    lineage_key = str(lineage_id).strip()
    for block in reversed(block_entries):
        if not isinstance(block, dict):
            continue
        block_index = _positive_int(block.get("block_index"), 0)
        if block_index < target_block:
            continue
        block_lineage = str(block.get("lineage_id", "")).strip()
        if lineage_key and block_lineage and block_lineage != lineage_key:
            continue
        return block
    return None


def reconcile_checkpoint_items_from_blocks(
    checkpoint_items: list[dict[str, Any]],
    block_entries: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    blocks = [entry for entry in (block_entries or []) if isinstance(entry, dict)]
    reconciled: list[dict[str, Any]] = []
    changed = False
    for item in checkpoint_items:
        if not isinstance(item, dict):
            changed = True
            continue
        normalized = deepcopy(item)
        raw_deadline_at = str(item.get("deadline_at", ""))
        normalized["deadline_at"] = raw_deadline_at.strip()
        if normalized["deadline_at"] != raw_deadline_at:
            changed = True
        raw_status = str(item.get("status", "")).strip().lower()
        status = _checkpoint_status_text(item.get("status"))
        normalized["status"] = status
        if status != raw_status:
            changed = True
        target_block = _positive_int(normalized.get("target_block"), 0)
        lineage_id = str(normalized.get("lineage_id", "")).strip()
        if not blocks or target_block <= 0 or status in {"approved", "failed"}:
            reconciled.append(normalized)
            continue
        latest_block = _latest_checkpoint_block(blocks, target_block, lineage_id)
        if latest_block is None:
            reconciled.append(normalized)
            continue
        block_status = str(latest_block.get("status", "")).strip().lower()
        if block_status == "completed":
            if status == "pending":
                normalized["status"] = "awaiting_review"
                changed = True
            reached_at = str(latest_block.get("completed_at") or latest_block.get("started_at") or "").strip()
            if reached_at and not str(normalized.get("reached_at", "")).strip():
                normalized["reached_at"] = reached_at
                changed = True
            commit_hashes = latest_block.get("commit_hashes", [])
            if isinstance(commit_hashes, list):
                normalized_commit_hashes = [str(item).strip() for item in commit_hashes if str(item).strip()]
                if normalized_commit_hashes and normalized.get("commit_hashes") != normalized_commit_hashes:
                    normalized["commit_hashes"] = normalized_commit_hashes
                    changed = True
            candidate_lineage = str(latest_block.get("lineage_id", "")).strip()
            if candidate_lineage and not lineage_id:
                normalized["lineage_id"] = candidate_lineage
                changed = True
        reconciled.append(normalized)
    return reconciled, changed


def resolve_execution_flow_steps(
    steps: list[ExecutionStep],
    block_entries: list[dict[str, Any]] | None = None,
) -> list[ExecutionStep]:
    latest_blocks = block_entries if block_entries is not None else []
    resolved: list[ExecutionStep] = []
    for step in steps:
        resolved_step = deepcopy(step)
        step_metadata = resolved_step.metadata if isinstance(resolved_step.metadata, dict) else {}
        lineage_id = str(step_metadata.get("lineage_id", "")).strip()
        latest_block = _latest_block_for_lineage(latest_blocks, lineage_id)
        if latest_block is not None:
            resolved_step.status = _flow_status_to_palette(str(latest_block.get("status") or resolved_step.status))
            resolved_step.notes = str(latest_block.get("test_summary") or resolved_step.notes or "").strip()
            commit_hashes = latest_block.get("commit_hashes", [])
            if isinstance(commit_hashes, list) and commit_hashes:
                resolved_step.commit_hash = str(commit_hashes[-1]).strip() or resolved_step.commit_hash
            completed_at = str(latest_block.get("completed_at") or "").strip()
            if completed_at:
                resolved_step.completed_at = completed_at
            started_at = str(latest_block.get("started_at") or "").strip()
            if started_at:
                resolved_step.started_at = started_at
        else:
            resolved_step.status = _flow_status_to_palette(resolved_step.status)
        resolved.append(resolved_step)
    return resolved


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
    if not checkpoints:
        lines.extend(
            [
                "No checkpoints recorded yet.",
                "",
            ]
        )
        return "\n".join(lines)
    for checkpoint in checkpoints:
        refs = ", ".join(checkpoint.plan_refs) if checkpoint.plan_refs else "none"
        lines.extend(
            [
                f"## {checkpoint.checkpoint_id}",
                f"- Title: {checkpoint.title}",
                f"- Target block: {checkpoint.target_block}",
                f"- Lineage: {checkpoint.lineage_id or 'n/a'}",
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
        normalize_execution_step_policy(step)
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
                f"  - Step type: {step.step_type or 'feature'}",
                f"  - Scope class: {step.scope_class or 'free_owned'}",
                f"  - Spine version: {step.spine_version or 'spine-v1'}",
                f"  - Shared contracts: {', '.join(step.shared_contracts) if step.shared_contracts else 'none'}",
                f"  - Model provider: {configured_provider} -> {step_model.provider} ({step_model.reason})",
                f"  - Model: {configured_model} -> {step_model.model or 'provider default'}",
                f"  - GPT reasoning: {step.reasoning_effort or context.runtime.effort or 'high'}",
                f"  - Status: {_checkpoint_status_text(step.status)}",
                f"  - Parallel group: {step.parallel_group or 'none'}",
                f"  - Depends on: {', '.join(step.depends_on) if step.depends_on else 'none'}",
                f"  - Owned paths: {', '.join(step.owned_paths) if step.owned_paths else 'none declared'}",
                f"  - Shared-reviewed paths: {', '.join(step.shared_reviewed_paths) if step.shared_reviewed_paths else 'none'}",
                f"  - Forbidden-core paths: {', '.join(step.forbidden_core_paths) if step.forbidden_core_paths else 'none'}",
                f"  - Verification: {step.test_command or 'Use the default test command.'}",
                f"  - Verification profile: {step.verification_profile or 'default'}",
                f"  - Success criteria: {step.success_criteria or 'Verification command completes successfully.'}",
                f"  - Declared promotion class: {step.promotion_class or 'green'}",
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
            status = _flow_status_to_palette(step.status)
            fill, text_fill = palette[status]
            title_lines = wrap_svg_text(compact_text(step.title, 90), 24, max_lines=2)
            detail_source = step.display_description or (", ".join(step.depends_on) if step.depends_on else "")
            if not detail_source and step.owned_paths:
                detail_source = f"{len(step.owned_paths)} owned path(s)"
            lineage_id = str((step.metadata or {}).get("lineage_id", "")).strip()
            if lineage_id:
                detail_source = f"{detail_source} | lineage {lineage_id}" if detail_source else f"lineage {lineage_id}"
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
        status = _flow_status_to_palette(step.status)
        fill, text_fill = palette[status]
        title_lines = wrap_svg_text(compact_text(step.title, 90), 24, max_lines=2)
        detail_lines = wrap_svg_text(
            compact_text(
                (
                    f"{step.display_description or step.parallel_group or step.test_command or 'default verification'}"
                    + (
                        f" | lineage {str((step.metadata or {}).get('lineage_id', '')).strip()}"
                        if str((step.metadata or {}).get("lineage_id", "")).strip()
                        else ""
                    )
                ),
                96,
            ),
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
