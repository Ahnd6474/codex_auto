from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .process_supervisor import hidden_window_creationflags, terminate_process
from .utils import decode_process_output, now_utc_iso, read_json, write_json


DEFAULT_TUNNEL_COMMAND = "cloudflared"
DEFAULT_TUNNEL_START_TIMEOUT_SECS = 12.0
TRYCLOUDFLARE_URL_RE = re.compile(r"https://[-a-z0-9]+\.trycloudflare\.com", re.IGNORECASE)


def public_tunnel_state_file(workspace_root: Path) -> Path:
    return workspace_root / "public_tunnel.json"


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


def start_cloudflare_quick_tunnel(workspace_root: Path, target_url: str, cloudflared_path: str = DEFAULT_TUNNEL_COMMAND) -> dict[str, Any]:
    resolved_target = str(target_url).strip().rstrip("/")
    if not resolved_target:
        raise ValueError("target_url is required.")

    current = public_tunnel_status_payload(workspace_root)
    if current.get("running") and current.get("target_url") == resolved_target:
        return current
    if current.get("running"):
        stop_public_tunnel_process(workspace_root)

    resolved_command = resolve_cloudflared_path(cloudflared_path)
    if not resolved_command:
        raise RuntimeError("cloudflared is not installed or not on PATH.")

    command = [resolved_command, "tunnel", "--url", resolved_target, "--no-autoupdate"]
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=hidden_window_creationflags(),
    )
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
