from __future__ import annotations

import hashlib
from html import escape
import json
import locale
import os
import re
import shutil
import stat
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UTC = getattr(datetime, "UTC", timezone.utc)
_ATOMIC_REPLACE_RETRY_DELAYS = (0.02, 0.05, 0.1, 0.2, 0.35)


def now_utc_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def slugify(value: str, max_length: int = 64) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    if not normalized:
        normalized = "repo"
    return normalized[:max_length].strip("-") or "repo"


def stable_repo_identity(repo_url: str, branch: str) -> tuple[str, str]:
    digest = hashlib.sha1(f"{repo_url}|{branch}".encode("utf-8")).hexdigest()
    stripped_repo_url = str(repo_url or "").strip().rstrip("/\\")
    name_seed = re.split(r"[\\/]+", stripped_repo_url)[-1] if stripped_repo_url else ""
    if name_seed.endswith(".git"):
        name_seed = name_seed[:-4]
    slug = f"{slugify(name_seed)}-{slugify(branch, max_length=20)}-{digest[:10]}"
    return digest, slug


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _is_transient_atomic_replace_error(exc: OSError) -> bool:
    winerror = getattr(exc, "winerror", None)
    if winerror in {5, 32}:
        return True
    return getattr(exc, "errno", None) in {13, 16}


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    ensure_dir(path.parent)
    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            delete=False,
            dir=str(path.parent),
            prefix=".tmp-",
            suffix=".tmp",
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = handle.name
        for attempt_index, delay in enumerate((*_ATOMIC_REPLACE_RETRY_DELAYS, None)):
            try:
                os.replace(temp_path, path)
                temp_path = None
                break
            except OSError as exc:
                if delay is None or not _is_transient_atomic_replace_error(exc):
                    raise
                time.sleep(delay)
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass


def write_text(path: Path, content: str) -> None:
  _atomic_write_bytes(path, content.encode("utf-8"))


def write_text_if_changed(path: Path, content: str) -> bool:
    if read_text(path) == content:
        return False
    write_text(path, content)
    return True


def append_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(content)


def decode_text_bytes(data: bytes) -> str:
    if not data:
        return ""
    preferred_encodings: list[str] = ["utf-8", "utf-8-sig"]
    locale_encoding = locale.getpreferredencoding(False)
    if locale_encoding and locale_encoding.lower() not in {"utf-8", "utf8"}:
        preferred_encodings.append(locale_encoding)
    for encoding in ("cp949", "cp1252"):
        if encoding not in preferred_encodings:
            preferred_encodings.append(encoding)
    for encoding in preferred_encodings:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def read_text(path: Path, default: str = "") -> str:
    if not path.exists():
        return default
    try:
        return decode_text_bytes(path.read_bytes())
    except OSError:
        return default


def write_json(path: Path, data: Any) -> None:
    _atomic_write_bytes(path, json.dumps(data, indent=2, sort_keys=True).encode("utf-8"))


def write_json_if_changed(path: Path, data: Any) -> bool:
    serialized = json.dumps(data, indent=2, sort_keys=True)
    if read_text(path) == serialized:
        return False
    _atomic_write_bytes(path, serialized.encode("utf-8"))
    return True


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(read_text(path))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return default


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
    for line in read_text(path).splitlines():
        payload = _parse_jsonl_line(line)
        if payload is not None:
            entries.append(payload)
    return entries


def _iter_jsonl_lines_from_end(path: Path, chunk_size: int = 8192):
    file_size = path.stat().st_size
    if file_size <= 0:
        return
    with path.open("rb") as handle:
        position = file_size
        remainder = b""
        while position > 0:
            read_size = min(chunk_size, position)
            position -= read_size
            handle.seek(position)
            chunk = handle.read(read_size)
            buffer = chunk + remainder
            parts = buffer.split(b"\n")
            remainder = parts[0]
            for line in reversed(parts[1:]):
                yield decode_text_bytes(line.rstrip(b"\r"))
        if remainder:
            yield decode_text_bytes(remainder.rstrip(b"\r"))


def read_jsonl_tail(path: Path, limit: int) -> list[dict[str, Any]]:
    if limit <= 0 or not path.exists():
        return []
    tail: list[dict[str, Any]] = []
    for line in _iter_jsonl_lines_from_end(path):
        payload = _parse_jsonl_line(line)
        if payload is None:
            continue
        tail.append(payload)
        if len(tail) >= limit:
            break
    tail.reverse()
    return tail


def read_last_jsonl(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    for line in _iter_jsonl_lines_from_end(path):
        payload = _parse_jsonl_line(line)
        if payload is not None:
            return payload
    return None


def decode_process_output(data: bytes) -> str:
    return decode_text_bytes(data)


def sanitized_subprocess_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    # Desktop bridge launches the backend with repo-local PYTHONPATH so this
    # project can import itself. Child processes operating on managed repos
    # should not inherit that path and accidentally import the wrong package.
    env.pop("PYTHONPATH", None)
    if extra:
        env.update(extra)
    return env


def remove_tree(path: Path, ignore_errors: bool = False) -> None:
    target = Path(path)
    if not target.exists():
        return

    def _handle_remove_readonly(func, failed_path, exc_info) -> None:
        try:
            os.chmod(failed_path, stat.S_IWRITE | stat.S_IREAD)
            func(failed_path)
        except OSError:
            if ignore_errors:
                return
            raise exc_info[1]

    shutil.rmtree(target, ignore_errors=ignore_errors, onerror=_handle_remove_readonly)


def compact_text(value: str, max_chars: int = 3_000) -> str:
    stripped = value.strip()
    if len(stripped) <= max_chars:
        return stripped
    return f"{stripped[: max_chars - 3].rstrip()}..."


def compact_text_balanced(
    value: str,
    max_chars: int = 3_000,
    *,
    tail_ratio: float = 0.55,
    separator: str = "\n...\n",
) -> str:
    stripped = value.strip()
    if len(stripped) <= max_chars:
        return stripped
    if max_chars <= len(separator) + 2:
        return compact_text(stripped, max_chars)
    normalized_tail_ratio = min(0.8, max(0.2, float(tail_ratio)))
    content_budget = max_chars - len(separator)
    tail_chars = max(1, int(content_budget * normalized_tail_ratio))
    head_chars = max(1, content_budget - tail_chars)
    if head_chars + tail_chars >= len(stripped):
        return stripped
    head = stripped[:head_chars].rstrip()
    tail = stripped[-tail_chars:].lstrip()
    return f"{head}{separator}{tail}"


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
    for raw_line in read_text(dotenv_path).splitlines():
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
