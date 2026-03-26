from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..orchestrator import Orchestrator


@dataclass(slots=True)
class BridgeCommandContext:
    workspace_root: Path
    payload: dict[str, Any]
    orchestrator: Orchestrator
    detail_payload: Callable[..., dict[str, Any]]


BridgeCommandHandler = Callable[[BridgeCommandContext], dict[str, Any]]

