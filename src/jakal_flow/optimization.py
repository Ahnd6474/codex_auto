from __future__ import annotations

import ast
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


CODE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx"}
EXCLUDED_DIR_NAMES = {
    ".git",
    ".idea",
    ".next",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "third_party",
}
MAX_SCAN_FILES = 400
BRANCH_NODE_TYPES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.Match,
    ast.With,
    ast.AsyncWith,
)
BOTTLENECK_PATTERNS = (
    ".glob(",
    ".rglob(",
    ".read_bytes(",
    ".read_text(",
    "json.load(",
    "load_project_by_",
    "os.walk(",
    "read_json(",
    "read_jsonl_tail(",
    "read_last_jsonl(",
)
LINE_LITERAL_PATTERN = re.compile(r"(['\"])(?:\\.|(?!\1).)*\1")
NUMBER_PATTERN = re.compile(r"\b\d+\b")
WHITESPACE_PATTERN = re.compile(r"\s+")


@dataclass(slots=True)
class OptimizationCandidate:
    category: str
    path: str
    summary: str
    details: str
    score: int
    line: int = 0
    symbol: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class OptimizationScanResult:
    mode: str
    scanned_file_count: int
    candidate_files: list[str]
    candidates: list[OptimizationCandidate]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "scanned_file_count": self.scanned_file_count,
            "candidate_files": list(self.candidate_files),
            "candidates": [item.to_dict() for item in self.candidates],
        }


@dataclass(slots=True)
class _CodeSnapshot:
    path: Path
    relative_path: str
    line_count: int
    text: str


def normalize_optimization_mode(value: str | None, fallback: str = "off") -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"off", "light", "refactor"}:
        return normalized
    return fallback


def scan_optimization_candidates(repo_dir: Path, runtime: Any) -> OptimizationScanResult:
    mode = normalize_optimization_mode(getattr(runtime, "optimization_mode", "off"))
    if mode == "off":
        return OptimizationScanResult(mode=mode, scanned_file_count=0, candidate_files=[], candidates=[])

    large_file_lines = max(50, int(getattr(runtime, "optimization_large_file_lines", 350) or 350))
    long_function_lines = max(25, int(getattr(runtime, "optimization_long_function_lines", 80) or 80))
    duplicate_block_lines = max(3, int(getattr(runtime, "optimization_duplicate_block_lines", 4) or 4))
    max_files = max(1, int(getattr(runtime, "optimization_max_files", 3) or 3))

    snapshots = _collect_code_snapshots(repo_dir)
    candidates: list[OptimizationCandidate] = []
    candidates.extend(_scan_large_files(snapshots, large_file_lines))
    candidates.extend(_scan_duplicate_blocks(snapshots, duplicate_block_lines))
    candidates.extend(_scan_python_functions(snapshots, long_function_lines))

    selected = _limit_candidates(candidates, max_files=max_files, mode=mode)
    candidate_files = sorted({item.path for item in selected})
    return OptimizationScanResult(
        mode=mode,
        scanned_file_count=len(snapshots),
        candidate_files=candidate_files,
        candidates=selected,
    )


def _collect_code_snapshots(repo_dir: Path) -> list[_CodeSnapshot]:
    snapshots: list[_CodeSnapshot] = []
    for root, dirnames, filenames in os.walk(repo_dir):
        dirnames[:] = [
            name
            for name in dirnames
            if name not in EXCLUDED_DIR_NAMES and not name.startswith(".jakal-flow")
        ]
        current_root = Path(root)
        for filename in sorted(filenames):
            path = current_root / filename
            if path.suffix.lower() not in CODE_SUFFIXES:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            relative_path = path.relative_to(repo_dir).as_posix()
            line_count = len(text.splitlines()) or (1 if text else 0)
            snapshots.append(
                _CodeSnapshot(
                    path=path,
                    relative_path=relative_path,
                    line_count=line_count,
                    text=text,
                )
            )
            if len(snapshots) >= MAX_SCAN_FILES:
                return snapshots
    return snapshots


def _scan_large_files(snapshots: list[_CodeSnapshot], threshold: int) -> list[OptimizationCandidate]:
    candidates: list[OptimizationCandidate] = []
    for snapshot in snapshots:
        if snapshot.line_count < threshold:
            continue
        candidates.append(
            OptimizationCandidate(
                category="large_file",
                path=snapshot.relative_path,
                line=snapshot.line_count,
                summary=f"Large file with {snapshot.line_count} lines",
                details="Split unrelated responsibilities into smaller modules or focused helpers before closeout.",
                score=max(1, snapshot.line_count // max(1, threshold)),
            )
        )
    return candidates


def _scan_duplicate_blocks(snapshots: list[_CodeSnapshot], window_lines: int) -> list[OptimizationCandidate]:
    occurrences: dict[str, list[tuple[str, int]]] = {}
    for snapshot in snapshots:
        normalized_lines = [
            (line_no, normalized)
            for line_no, normalized in _normalized_code_lines(snapshot.text)
            if normalized
        ]
        for index in range(0, len(normalized_lines) - window_lines + 1):
            window = normalized_lines[index : index + window_lines]
            window_values = [value for _, value in window]
            if not _is_duplicate_window_candidate(window_values):
                continue
            key = "\n".join(window_values)
            occurrences.setdefault(key, []).append((snapshot.relative_path, window[0][0]))

    candidates: list[OptimizationCandidate] = []
    for locations in occurrences.values():
        unique_locations = list(dict.fromkeys(locations))
        if len(unique_locations) < 2:
            continue
        reference_path, reference_line = unique_locations[0]
        duplicate_path, duplicate_line = unique_locations[1]
        candidates.append(
            OptimizationCandidate(
                category="duplicate",
                path=duplicate_path,
                line=duplicate_line,
                summary=f"Repeated logic also seen in {reference_path}:{reference_line}",
                details="Consider extracting a shared helper or consolidating the duplicated block.",
                score=len(unique_locations),
            )
        )
    return candidates


def _scan_python_functions(snapshots: list[_CodeSnapshot], long_function_lines: int) -> list[OptimizationCandidate]:
    candidates: list[OptimizationCandidate] = []
    branch_threshold = 5
    bottleneck_threshold = 3
    for snapshot in snapshots:
        if snapshot.path.suffix.lower() != ".py":
            continue
        try:
            tree = ast.parse(snapshot.text)
        except SyntaxError:
            continue
        lines = snapshot.text.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            start = int(getattr(node, "lineno", 1) or 1)
            end = int(getattr(node, "end_lineno", start) or start)
            span = max(1, end - start + 1)
            snippet = "\n".join(lines[start - 1 : end])
            branch_count = sum(1 for child in ast.walk(node) if isinstance(child, BRANCH_NODE_TYPES))
            bottleneck_score = sum(snippet.count(pattern) for pattern in BOTTLENECK_PATTERNS)
            symbol = node.name
            if span >= long_function_lines or branch_count >= branch_threshold:
                candidates.append(
                    OptimizationCandidate(
                        category="multi_responsibility",
                        path=snapshot.relative_path,
                        line=start,
                        symbol=symbol,
                        summary=f"Function {symbol} spans {span} lines with {branch_count} branch points",
                        details="Split orchestration, I/O, and formatting concerns into smaller units with a single responsibility.",
                        score=max(span // max(1, long_function_lines), 1) + branch_count,
                    )
                )
            if bottleneck_score >= bottleneck_threshold and span >= max(20, long_function_lines // 2):
                candidates.append(
                    OptimizationCandidate(
                        category="bottleneck",
                        path=snapshot.relative_path,
                        line=start,
                        symbol=symbol,
                        summary=f"Function {symbol} mixes {bottleneck_score} filesystem or repository scan signals",
                        details="Cache, narrow, or extract repeated file-system and repository reads to keep closeout lightweight.",
                        score=bottleneck_score + branch_count,
                    )
                )
    return candidates


def _normalized_code_lines(text: str) -> list[tuple[int, str]]:
    normalized: list[tuple[int, str]] = []
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith(("#", "//", "/*", "*", "*/")):
            continue
        without_literals = LINE_LITERAL_PATTERN.sub('"..."', stripped)
        without_numbers = NUMBER_PATTERN.sub("0", without_literals)
        compact = WHITESPACE_PATTERN.sub(" ", without_numbers).strip()
        if compact:
            normalized.append((line_no, compact))
    return normalized


def _is_duplicate_window_candidate(lines: list[str]) -> bool:
    if len(lines) < 3:
        return False
    if sum(len(line) for line in lines) < 80:
        return False
    if sum(1 for line in lines if line in {"{", "}", "[", "]", "(", ")"}) > 0:
        return False
    if sum(1 for line in lines if line.startswith(("import ", "from ", "export "))) > 1:
        return False
    return True


def _limit_candidates(
    candidates: list[OptimizationCandidate],
    *,
    max_files: int,
    mode: str,
) -> list[OptimizationCandidate]:
    category_priority = {
        "bottleneck": 0,
        "multi_responsibility": 1,
        "duplicate": 2,
        "large_file": 3,
    }
    per_file_limit = 3 if mode == "refactor" else 2
    total_limit = max_files * per_file_limit
    selected: list[OptimizationCandidate] = []
    selected_paths: list[str] = []
    path_counts: dict[str, int] = {}
    seen: set[tuple[str, str, int, str]] = set()
    for candidate in sorted(
        candidates,
        key=lambda item: (
            category_priority.get(item.category, 9),
            -item.score,
            item.path,
            item.line,
            item.summary,
        ),
    ):
        signature = (candidate.category, candidate.path, candidate.line, candidate.summary)
        if signature in seen:
            continue
        seen.add(signature)
        if candidate.path not in selected_paths and len(selected_paths) >= max_files:
            continue
        if candidate.path not in selected_paths:
            selected_paths.append(candidate.path)
        if path_counts.get(candidate.path, 0) >= per_file_limit:
            continue
        path_counts[candidate.path] = path_counts.get(candidate.path, 0) + 1
        selected.append(candidate)
        if len(selected) >= total_limit:
            break
    return selected
