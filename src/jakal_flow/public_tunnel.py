from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .process_supervisor import hidden_window_creationflags, hidden_window_startupinfo, terminate_process
from .utils import append_jsonl, decode_process_output, now_utc_iso, read_json, write_json


DEFAULT_TUNNEL_COMMAND = "cloudflared"
DEFAULT_TUNNEL_START_TIMEOUT_SECS = 12.0
DEFAULT_TUNNEL_INSTALL_TIMEOUT_SECS = 180.0
DEFAULT_CLOUDFLARED_PACKAGE_ID = "Cloudflare.cloudflared"
TRYCLOUDFLARE_URL_RE = re.compile(r"https://[-a-z0-9]+\.trycloudflare\.com", re.IGNORECASE)


def public_tunnel_state_file(workspace_root: Path) -> Path:
    return workspace_root / "public_tunnel.json"


def public_tunnel_install_log_file(workspace_root: Path) -> Path:
    return workspace_root / "public_tunnel_installs.jsonl"


@dataclass(slots=True)
class PublicTunnelState:
    provider: str
    public_url: str
    target_url: str
    pid: int
    started_at: str
    command: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PublicTunnelState":
        command = data.get("command", [])
        return cls(
            provider=str(data.get("provider", "cloudflare-quick-tunnel")).strip() or "cloudflare-quick-tunnel",
            public_url=str(data.get("public_url", "")).strip(),
            target_url=str(data.get("target_url", "")).strip(),
            pid=int(data.get("pid", 0) or 0),
            started_at=str(data.get("started_at", "")).strip(),
            command=[str(item).strip() for item in command if str(item).strip()] if isinstance(command, list) else [],
        )


def process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        completed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            check=False,
            capture_output=True,
        )
        stdout = decode_process_output(completed.stdout)
        return f"{pid}" in stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def load_public_tunnel_state(workspace_root: Path) -> PublicTunnelState | None:
    raw = read_json(public_tunnel_state_file(workspace_root), default=None)
    if not isinstance(raw, dict):
        return None
    try:
        return PublicTunnelState.from_dict(raw)
    except (TypeError, ValueError):
        return None


def save_public_tunnel_state(workspace_root: Path, state: PublicTunnelState) -> PublicTunnelState:
    write_json(public_tunnel_state_file(workspace_root), state.to_dict())
    return state


def clear_public_tunnel_state(workspace_root: Path) -> None:
    try:
        public_tunnel_state_file(workspace_root).unlink(missing_ok=True)
    except OSError:
        pass


def public_tunnel_status_payload(workspace_root: Path) -> dict[str, Any]:
    state = load_public_tunnel_state(workspace_root)
    available_path = resolve_cloudflared_path()
    if state is None:
        return {
            "running": False,
            "provider": "cloudflare-quick-tunnel",
            "public_url": None,
            "target_url": None,
            "pid": None,
            "started_at": None,
            "available": available_path is not None,
            "command_path": available_path,
        }
    running = process_is_running(state.pid)
    payload = {
        "running": running,
        "provider": state.provider,
        "public_url": state.public_url if running else None,
        "target_url": state.target_url if running else None,
        "pid": state.pid if running else None,
        "started_at": state.started_at if running else None,
        "available": available_path is not None,
        "command_path": available_path,
    }
    if not running:
        clear_public_tunnel_state(workspace_root)
    return payload


def shutil_which(command: str) -> str | None:
    from shutil import which

    return which(command)


def resolve_winget_path() -> str | None:
    direct = shutil_which("winget")
    if direct:
        return direct
    if os.name != "nt":
        return None
    local_appdata = Path(os.environ.get("LOCALAPPDATA", "")).expanduser()
    if not local_appdata:
        return None
    candidate = local_appdata / "Microsoft" / "WindowsApps" / "winget.exe"
    if candidate.is_file():
        return str(candidate)
    return None


def resolve_cloudflared_path(candidate: str = DEFAULT_TUNNEL_COMMAND) -> str | None:
    direct = shutil_which(candidate)
    if direct:
        return direct
    if os.name != "nt":
        return None
    local_appdata = Path(os.environ.get("LOCALAPPDATA", "")).expanduser()
    if not local_appdata:
        return None
    roots = [
        local_appdata / "Microsoft" / "WinGet" / "Packages",
        local_appdata / "Microsoft" / "WinGet" / "Links",
    ]
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("cloudflared.exe"):
            if path.is_file():
                return str(path)
    return None


def extract_trycloudflare_url(text: str) -> str | None:
    match = TRYCLOUDFLARE_URL_RE.search(text or "")
    return match.group(0) if match else None


def _installer_output_excerpt(stdout: str, stderr: str, max_chars: int = 400) -> str:
    parts = [str(stdout or "").strip(), str(stderr or "").strip()]
    combined = " | ".join(part for part in parts if part)
    if len(combined) <= max_chars:
        return combined
    return f"{combined[: max_chars - 3].rstrip()}..."


def _log_install_event(workspace_root: Path, event_type: str, **details: Any) -> None:
    append_jsonl(
        public_tunnel_install_log_file(workspace_root),
        {
            "timestamp": now_utc_iso(),
            "event_type": event_type,
            **details,
        },
    )


def install_cloudflared_with_winget(
    workspace_root: Path,
    package_id: str = DEFAULT_CLOUDFLARED_PACKAGE_ID,
) -> str:
    existing = resolve_cloudflared_path()
    if existing:
        return existing
    if os.name != "nt":
        raise RuntimeError("Automatic cloudflared installation is only supported on Windows.")
    winget_path = resolve_winget_path()
    if not winget_path:
        raise RuntimeError("cloudflared is not installed and winget is unavailable for automatic installation.")
    command = [
        winget_path,
        "install",
        "--id",
        package_id,
        "--exact",
        "--source",
        "winget",
        "--scope",
        "user",
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--disable-interactivity",
    ]
    _log_install_event(workspace_root, "cloudflared-install-started", command=command, package_id=package_id)
    run_kwargs: dict[str, Any] = {
        "check": False,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": DEFAULT_TUNNEL_INSTALL_TIMEOUT_SECS,
        "creationflags": hidden_window_creationflags(),
        "startupinfo": hidden_window_startupinfo(),
    }
    try:
        completed = subprocess.run(command, **run_kwargs)
    except subprocess.TimeoutExpired as exc:
        excerpt = _installer_output_excerpt(str(exc.stdout or ""), str(exc.stderr or ""))
        _log_install_event(
            workspace_root,
            "cloudflared-install-timeout",
            command=command,
            package_id=package_id,
            output_excerpt=excerpt,
        )
        raise RuntimeError("Automatic cloudflared installation timed out.") from exc
    except (OSError, ValueError):
        if os.name != "nt" or run_kwargs["startupinfo"] is None:
            raise
        run_kwargs["startupinfo"] = None
        completed = subprocess.run(command, **run_kwargs)
    stdout = str(completed.stdout or "")
    stderr = str(completed.stderr or "")
    excerpt = _installer_output_excerpt(stdout, stderr)
    if completed.returncode != 0:
        _log_install_event(
            workspace_root,
            "cloudflared-install-failed",
            command=command,
            package_id=package_id,
            returncode=int(completed.returncode),
            output_excerpt=excerpt,
        )
        detail = f" {excerpt}" if excerpt else ""
        raise RuntimeError(
            f"Automatic cloudflared installation failed via winget (exit {completed.returncode}).{detail}".strip()
        )
    resolved = resolve_cloudflared_path()
    if not resolved:
        _log_install_event(
            workspace_root,
            "cloudflared-install-missing-binary",
            command=command,
            package_id=package_id,
            output_excerpt=excerpt,
        )
        raise RuntimeError("cloudflared installation reported success, but the executable could not be found afterward.")
    _log_install_event(
        workspace_root,
        "cloudflared-install-succeeded",
        command=command,
        package_id=package_id,
        command_path=resolved,
        output_excerpt=excerpt,
    )
    return resolved


def ensure_cloudflared_path(workspace_root: Path, candidate: str = DEFAULT_TUNNEL_COMMAND) -> str:
    resolved = resolve_cloudflared_path(candidate)
    if resolved:
        return resolved
    candidate_text = str(candidate or "").strip()
    candidate_name = Path(candidate_text).name.lower() if candidate_text else DEFAULT_TUNNEL_COMMAND
    if candidate_name not in {"cloudflared", "cloudflared.exe"}:
        raise RuntimeError(f"cloudflared executable was not found: {candidate_text}")
    if os.name == "nt":
        return install_cloudflared_with_winget(workspace_root)
    raise RuntimeError("cloudflared is not installed or not on PATH.")


def normalize_tunnel_target_url(target_url: str) -> str:
    text = str(target_url).strip().rstrip("/")
    if not text:
        return ""
    parsed = urlsplit(text)
    if parsed.hostname != "0.0.0.0":
        return text
    port = f":{parsed.port}" if parsed.port is not None else ""
    netloc = f"127.0.0.1{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment)).rstrip("/")


def start_cloudflare_quick_tunnel(workspace_root: Path, target_url: str, cloudflared_path: str = DEFAULT_TUNNEL_COMMAND) -> dict[str, Any]:
    resolved_target = normalize_tunnel_target_url(target_url)
    if not resolved_target:
        raise ValueError("target_url is required.")

    current = public_tunnel_status_payload(workspace_root)
    if current.get("running") and current.get("target_url") == resolved_target:
        return current
    if current.get("running"):
        stop_public_tunnel_process(workspace_root)

    resolved_command = ensure_cloudflared_path(workspace_root, cloudflared_path)

    command = [resolved_command, "tunnel", "--url", resolved_target, "--no-autoupdate"]
    popen_kwargs = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "bufsize": 1,
        "creationflags": hidden_window_creationflags(),
        "startupinfo": hidden_window_startupinfo(),
    }
    try:
        process = subprocess.Popen(command, **popen_kwargs)
    except (OSError, ValueError):
        if os.name != "nt" or popen_kwargs["startupinfo"] is None:
            raise
        popen_kwargs["startupinfo"] = None
        process = subprocess.Popen(command, **popen_kwargs)
    assert process.stdout is not None

    deadline = time.monotonic() + DEFAULT_TUNNEL_START_TIMEOUT_SECS
    buffered_lines: list[str] = []
    public_url = None
    while time.monotonic() < deadline:
        line = process.stdout.readline()
        if line:
            buffered_lines.append(line.strip())
            public_url = extract_trycloudflare_url(line)
            if public_url:
                break
        elif process.poll() is not None:
            break
        else:
            time.sleep(0.1)
    if not public_url:
        try:
            process.terminate()
            process.wait(timeout=1.5)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
        excerpt = " | ".join(line for line in buffered_lines if line) or "No startup output."
        raise RuntimeError(f"Could not start Cloudflare Quick Tunnel. {excerpt}")

    state = PublicTunnelState(
        provider="cloudflare-quick-tunnel",
        public_url=public_url.rstrip("/"),
        target_url=resolved_target,
        pid=int(process.pid or 0),
        started_at=now_utc_iso(),
        command=command,
    )
    save_public_tunnel_state(workspace_root, state)
    return public_tunnel_status_payload(workspace_root)


def stop_public_tunnel_process(workspace_root: Path) -> dict[str, Any]:
    status = public_tunnel_status_payload(workspace_root)
    pid = int(status.get("pid") or 0)
    if pid > 0:
        terminate_process(pid)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if not process_is_running(pid):
                break
            time.sleep(0.1)
    clear_public_tunnel_state(workspace_root)
    return public_tunnel_status_payload(workspace_root)
