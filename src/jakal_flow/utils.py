from __future__ import annotations

import hashlib
from html import escape
import json
import locale
import os
import re
from collections import deque
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


def _balanced_json_fragment(text: str, start: int) -> str | None:
    opening = text[start]
    if opening not in "{[":
        return None
    expected_closer = "}" if opening == "{" else "]"
    stack = [expected_closer]
    in_string = False
    escaped = False
    for index in range(start + 1, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            stack.append("}")
            continue
        if char == "[":
            stack.append("]")
            continue
        if char in "}]":
            if not stack or char != stack[-1]:
                return None
            stack.pop()
            if not stack:
                return text[start : index + 1]
    return None


def _json_text_candidates(text: str) -> list[str]:
    raw = text.strip()
    if not raw:
        return []
    candidates: list[str] = [raw]
    fenced = re.search(r"```(?:json)?\s*(.+?)\s*```", raw, re.DOTALL)
    if fenced:
        fenced_text = fenced.group(1).strip()
        if fenced_text and fenced_text not in candidates:
            candidates.append(fenced_text)
    for source in list(candidates):
        for index, char in enumerate(source):
            if char not in "{[":
                continue
            fragment = _balanced_json_fragment(source, index)
            if fragment and fragment not in candidates:
                candidates.append(fragment)
    return candidates


def parse_json_text(text: str) -> Any:
    candidates = _json_text_candidates(text)
    last_error: json.JSONDecodeError | None = None
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return json.loads(text)


def _parse_jsonl_line(line: str) -> dict[str, Any] | None:
    raw = line.strip()
    if not raw:
        return None
    try:
        payload = parse_json_text(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


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
        payload = _parse_jsonl_line(line)
        if payload is not None:
            entries.append(payload)
    return entries


def read_jsonl_tail(path: Path, limit: int) -> list[dict[str, Any]]:
    if limit <= 0 or not path.exists():
        return []
    tail: deque[dict[str, Any]] = deque(maxlen=limit)
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            payload = _parse_jsonl_line(line)
            if payload is not None:
                tail.append(payload)
    return list(tail)


def read_last_jsonl(path: Path) -> dict[str, Any] | None:
    items = read_jsonl_tail(path, 1)
    if not items:
        return None
    return items[0]


def decode_process_output(data: bytes) -> str:
    if not data:
        return ""
    preferred_encodings: list[str] = ["utf-8"]
    locale_encoding = locale.getpreferredencoding(False)
    if locale_encoding and locale_encoding.lower() not in {"utf-8", "utf8"}:
        preferred_encodings.append(locale_encoding)
    for encoding in ("cp949", "utf-8-sig"):
        if encoding not in preferred_encodings:
            preferred_encodings.append(encoding)
    for encoding in preferred_encodings:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def compact_text(value: str, max_chars: int = 3_000) -> str:
    stripped = value.strip()
    if len(stripped) <= max_chars:
        return stripped
    return f"{stripped[: max_chars - 3].rstrip()}..."


def wrap_svg_text(value: str, max_chars_per_line: int, max_lines: int = 2) -> list[str]:
    normalized = re.sub(r"\s+", " ", value).strip()
    if not normalized or max_chars_per_line <= 0 or max_lines <= 0:
        return []
    words = normalized.split(" ")
    lines: list[str] = []
    current_words: list[str] = []
    index = 0
    while index < len(words):
        word = words[index]
        candidate = " ".join([*current_words, word]) if current_words else word
        if len(candidate) <= max_chars_per_line:
            current_words.append(word)
            index += 1
            continue
        if current_words:
            if len(lines) == max_lines - 1:
                lines.append(compact_text(" ".join([*current_words, *words[index:]]), max_chars_per_line))
                return lines
            lines.append(" ".join(current_words))
            current_words = []
            continue
        if len(lines) == max_lines - 1:
            lines.append(compact_text(word, max_chars_per_line))
            return lines
        lines.append(compact_text(word, max_chars_per_line))
        index += 1
    if current_words and len(lines) < max_lines:
        lines.append(" ".join(current_words))
    return lines


def svg_text_element(
    x: float,
    y: float,
    lines: list[str],
    *,
    fill: str,
    font_size: int,
    font_family: str,
    font_weight: str | int | None = None,
    line_height: int | None = None,
) -> str:
    if not lines:
        return ""
    weight_attr = f' font-weight="{font_weight}"' if font_weight is not None else ""
    dy = line_height or int(font_size * 1.3)
    first, *rest = lines
    tspans = "".join(f'<tspan x="{x}" dy="{dy}">{escape(line)}</tspan>' for line in rest)
    return (
        f'<text x="{x}" y="{y}" fill="{fill}" font-family="{font_family}" '
        f'font-size="{font_size}"{weight_attr}>{escape(first)}{tspans}</text>'
    )


def normalize_workflow_mode(value: Any, fallback: str = "standard") -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "ml":
        return "ml"
    return fallback if str(fallback).strip().lower() == "ml" else "standard"


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


def load_dotenv(dotenv_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not dotenv_path.exists():
        return values
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def get_env_or_dotenv(key: str, dotenv_path: Path) -> str:
    env_value = os.environ.get(key)
    if env_value:
        return env_value
    values = load_dotenv(dotenv_path)
    return values.get(key, "")
