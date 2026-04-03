from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import time
from typing import Iterable


_BUNDLED_PYTHON_LIB_IGNORES = {
    "__pycache__",
    "idlelib",
    "site-packages",
    "test",
    "tkinter",
    "turtledemo",
}
_BUNDLED_PYTHON_FILE_SUFFIX_IGNORES = {".pyc", ".pyo"}
_DEFAULT_REQUIRED_COMMANDS = ("codex.cmd",) if os.name == "nt" else ("codex",)
_DEFAULT_OPTIONAL_COMMANDS = ("gemini.cmd", "claude.cmd", "qwen.cmd") if os.name == "nt" else ("gemini", "claude", "qwen")
_SHIM_TARGET_PATTERN = re.compile(r"%dp0%\\(?P<relative>node_modules\\[^\"]+)", re.IGNORECASE)
_BUNDLED_PYTHON_DIRNAME = "py"
_BUNDLED_TOOLING_DIRNAME = "bin"
_REMOVE_TREE_ATTEMPTS = 8
_REMOVE_TREE_RETRY_DELAY_SECONDS = 0.25


@dataclass(frozen=True, slots=True)
class BundledPythonManifest:
    executable: str
    home: str
    version: str


@dataclass(frozen=True, slots=True)
class BundledToolManifest:
    command: str
    available: bool
    bundled_command: str
    package_name: str
    package_version: str
    source_command: str
    reason: str


@dataclass(frozen=True, slots=True)
class RuntimeBundleManifest:
    built_at: str
    target_dir: str
    python: BundledPythonManifest
    tools: list[BundledToolManifest]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_target_dir() -> Path:
    return repo_root() / "rt"


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _python_home() -> Path:
    candidates = [
        Path(getattr(sys, "base_prefix", "") or ""),
        Path(getattr(sys, "prefix", "") or ""),
        Path(sys.executable).resolve().parent,
    ]
    for candidate in candidates:
        if not str(candidate):
            continue
        if (candidate / "Lib").is_dir() and any((candidate / name).exists() for name in ("python.exe", "python3.dll")):
            return candidate
    raise RuntimeError("Failed to locate a Python installation root with Lib/ and python runtime files.")


def _python_root_files(source_home: Path) -> list[Path]:
    patterns = (
        "python*.exe",
        "python*.dll",
        "vcruntime*.dll",
        "msvcp*.dll",
        "ucrtbase.dll",
        "pyvenv.cfg",
    )
    matched: dict[str, Path] = {}
    for pattern in patterns:
        for item in source_home.glob(pattern):
            if item.is_file():
                matched[item.name.lower()] = item
    return sorted(matched.values(), key=lambda item: item.name.lower())


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _make_writable(path: Path | str) -> None:
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        return


def _prepare_tree_for_removal(target: Path) -> None:
    if not target.exists():
        return
    for root, dir_names, file_names in os.walk(target, topdown=False):
        current = Path(root)
        for file_name in file_names:
            _make_writable(current / file_name)
        for directory_name in dir_names:
            _make_writable(current / directory_name)
    _make_writable(target)


def _remove_tree(path: Path) -> None:
    target = Path(path)
    if not target.exists():
        return

    def _handle_remove_readonly(func, failed_path, exc_info) -> None:
        try:
            _make_writable(failed_path)
            func(failed_path)
        except OSError:
            raise exc_info[1]

    last_error: OSError | None = None
    for attempt in range(_REMOVE_TREE_ATTEMPTS):
        try:
            shutil.rmtree(target, onerror=_handle_remove_readonly)
            return
        except OSError as exc:
            last_error = exc
            _prepare_tree_for_removal(target)
            if not target.exists():
                return
            time.sleep(_REMOVE_TREE_RETRY_DELAY_SECONDS * (attempt + 1))
    if last_error is not None:
        raise last_error


def _copy_tree_filtered(source: Path, destination: Path, *, ignored_dir_names: set[str]) -> None:
    for root, dir_names, file_names in os.walk(source):
        current = Path(root)
        relative = current.relative_to(source)
        dir_names[:] = [
            name
            for name in dir_names
            if name not in ignored_dir_names and not name.startswith(".")
        ]
        destination_dir = destination / relative
        destination_dir.mkdir(parents=True, exist_ok=True)
        for file_name in file_names:
            if file_name in {"._pth"}:
                continue
            if Path(file_name).suffix.lower() in _BUNDLED_PYTHON_FILE_SUFFIX_IGNORES:
                continue
            _copy_file(current / file_name, destination_dir / file_name)


def _bundle_python_runtime(target_dir: Path) -> BundledPythonManifest:
    source_home = _python_home()
    destination_home = target_dir / _BUNDLED_PYTHON_DIRNAME
    if destination_home.exists():
        _remove_tree(destination_home)
    destination_home.mkdir(parents=True, exist_ok=True)

    for source_file in _python_root_files(source_home):
        _copy_file(source_file, destination_home / source_file.name)

    for directory_name in ("DLLs", "Lib"):
        source_dir = source_home / directory_name
        if not source_dir.is_dir():
            continue
        ignored_names = {"__pycache__"} if directory_name == "DLLs" else _BUNDLED_PYTHON_LIB_IGNORES
        _copy_tree_filtered(source_dir, destination_home / directory_name, ignored_dir_names=ignored_names)

    executable_name = "python.exe" if os.name == "nt" else "python"
    bundled_executable = destination_home / executable_name
    if not bundled_executable.exists():
        raise RuntimeError(f"Bundled Python executable is missing after copy: {bundled_executable}")
    return BundledPythonManifest(
        executable=str(bundled_executable),
        home=str(destination_home),
        version=sys.version.splitlines()[0],
    )


def _resolve_global_npm_root() -> Path | None:
    appdata = str(os.environ.get("APPDATA", "") or "").strip()
    if appdata:
        candidate = Path(appdata) / "npm"
        if candidate.is_dir():
            return candidate
    return None


def _bundled_tooling_bin(target_dir: Path) -> Path:
    return target_dir / _BUNDLED_TOOLING_DIRNAME


def _parse_shim_target(shim_path: Path) -> tuple[Path, Path] | None:
    try:
        text = shim_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = _SHIM_TARGET_PATTERN.search(text)
    if not match:
        return None
    relative_target = Path(match.group("relative").replace("\\", "/"))
    parts = relative_target.parts
    if len(parts) < 2 or parts[0] != "node_modules":
        return None
    package_end = 3 if len(parts) >= 3 and parts[1].startswith("@") else 2
    if len(parts) < package_end:
        return None
    return relative_target, Path(*parts[:package_end])


def _package_version(package_dir: Path) -> str:
    package_json = package_dir / "package.json"
    try:
        payload = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("version", "")).strip()


def _shim_candidate_names(command_name: str) -> list[str]:
    raw = str(command_name or "").strip()
    if not raw:
        return []
    candidates = [raw]
    stem = Path(raw).stem
    suffix = Path(raw).suffix.lower()
    if os.name == "nt":
        if suffix not in {".cmd", ".bat", ".exe"}:
            candidates.extend([f"{raw}.cmd", f"{raw}.exe"])
        if stem and stem != raw:
            candidates.append(stem)
    elif suffix:
        candidates.append(stem)
    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _locate_command_in_global_npm(command_name: str) -> Path | None:
    npm_root = _resolve_global_npm_root()
    if npm_root is None:
        resolved = shutil.which(command_name)
        return Path(resolved) if resolved else None
    for candidate_name in _shim_candidate_names(command_name):
        candidate = npm_root / candidate_name
        if candidate.exists():
            return candidate
    resolved = shutil.which(command_name)
    return Path(resolved) if resolved else None


def _copy_optional_peer(source_dir: Path, destination_dir: Path, file_name: str) -> None:
    source = source_dir / file_name
    if source.exists():
        _copy_file(source, destination_dir / file_name)


def _bundle_tool_command(target_dir: Path, command_name: str) -> BundledToolManifest:
    command_name = str(command_name or "").strip()
    tooling_bin = _bundled_tooling_bin(target_dir)
    tooling_bin.mkdir(parents=True, exist_ok=True)
    shim_source = _locate_command_in_global_npm(command_name)
    if shim_source is None:
        return BundledToolManifest(
            command=command_name,
            available=False,
            bundled_command="",
            package_name="",
            package_version="",
            source_command="",
            reason="command was not found in the global npm directory",
        )

    node_command = shutil.which("node")
    if not node_command:
        raise RuntimeError(f"Failed to bundle {command_name}: node.exe is not installed on the build machine.")
    node_source = Path(node_command)
    _copy_file(node_source, tooling_bin / node_source.name)
    _copy_optional_peer(node_source.parent, tooling_bin, "nodevars.bat")

    parsed_target = _parse_shim_target(shim_source)
    if parsed_target is None:
        raise RuntimeError(f"Failed to bundle {command_name}: could not parse shim target from {shim_source}.")
    _, package_relative_root = parsed_target
    source_npm_root = shim_source.parent
    package_source = source_npm_root / package_relative_root
    if not package_source.is_dir():
        raise RuntimeError(f"Failed to bundle {command_name}: package directory is missing: {package_source}")

    _copy_file(shim_source, tooling_bin / shim_source.name)
    if shim_source.suffix.lower() == ".cmd":
        companion = shim_source.with_suffix("")
        if companion.exists():
            _copy_file(companion, tooling_bin / companion.name)

    destination_package = tooling_bin / package_relative_root
    if destination_package.exists():
        _remove_tree(destination_package)
    shutil.copytree(package_source, destination_package, dirs_exist_ok=True)

    package_name = "/".join(package_relative_root.parts[1:])
    bundled_command = tooling_bin / shim_source.name
    return BundledToolManifest(
        command=command_name,
        available=True,
        bundled_command=str(bundled_command),
        package_name=package_name,
        package_version=_package_version(package_source),
        source_command=str(shim_source),
        reason="",
    )


def bundle_runtime(
    *,
    target_dir: Path | None = None,
    required_commands: Iterable[str] = _DEFAULT_REQUIRED_COMMANDS,
    optional_commands: Iterable[str] = _DEFAULT_OPTIONAL_COMMANDS,
    bundle_tools: bool = True,
) -> RuntimeBundleManifest:
    required = [str(command).strip() for command in required_commands if str(command).strip()]
    optional = [str(command).strip() for command in optional_commands if str(command).strip()]
    destination = Path(target_dir or default_target_dir())
    if destination.exists():
        _remove_tree(destination)
    destination.mkdir(parents=True, exist_ok=True)

    python_manifest = _bundle_python_runtime(destination)
    tools: list[BundledToolManifest] = []
    if bundle_tools:
        for command_name in [*required, *optional]:
            tools.append(_bundle_tool_command(destination, command_name))

        missing_required = [tool.command for tool in tools if tool.command in set(required) and not tool.available]
        if missing_required:
            missing_text = ", ".join(sorted(missing_required))
            raise RuntimeError(f"Failed to bundle required CLI command(s): {missing_text}")

    manifest = RuntimeBundleManifest(
        built_at=_now_utc_iso(),
        target_dir=str(destination),
        python=python_manifest,
        tools=tools,
    )
    (destination / "manifest.json").write_text(
        json.dumps(asdict(manifest), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare the bundled runtime used by the Tauri desktop installer.")
    parser.add_argument(
        "--target",
        default=str(default_target_dir()),
        help="Target directory that will receive the bundled runtime resources",
    )
    parser.add_argument(
        "--profile",
        choices=("full", "python"),
        default="full",
        help="Bundle profile: 'full' includes Python and detected CLI tooling, 'python' bundles only Python.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = bundle_runtime(
        target_dir=Path(args.target),
        bundle_tools=args.profile != "python",
    )
    print(json.dumps(asdict(manifest), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
