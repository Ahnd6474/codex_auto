from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def now_utc_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def slugify(value: str, max_length: int = 64) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    if not normalized:
        normalized = "repo"
    return normalized[:max_length].strip("-") or "repo"


def stable_repo_identity(repo_url: str, branch: str) -> tuple[str, str]:
    digest = hashlib.sha1(f"{repo_url}|{branch}".encode("utf-8")).hexdigest()
    name_seed = repo_url.rstrip("/").split("/")[-1]
    if name_seed.endswith(".git"):
        name_seed = name_seed[:-4]
    slug = f"{slugify(name_seed)}-{slugify(branch, max_length=20)}-{digest[:10]}"
    return digest, slug


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")


def append_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(content)


def read_text(path: Path, default: str = "") -> str:
    if not path.exists():
        return default
    return path.read_text(encoding="utf-8")


def write_json(path: Path, data: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def append_jsonl(path: Path, data: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(data, sort_keys=True))
        handle.write("\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(json.loads(line))
    return entries


def compact_text(value: str, max_chars: int = 3_000) -> str:
    stripped = value.strip()
    if len(stripped) <= max_chars:
        return stripped
    return f"{stripped[: max_chars - 3].rstrip()}..."


def tokenize(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-Z0-9_]+", value.lower()) if len(token) > 2}


def similarity_score(left: str, right: str) -> float:
    left_tokens = tokenize(left)
    right_tokens = tokenize(right)
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = left_tokens & right_tokens
    union = left_tokens | right_tokens
    return len(intersection) / len(union)
