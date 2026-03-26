from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any


BRIDGE_PROTOCOL_VERSION = 1
BRIDGE_EVENT_NAME = "jakal-flow://bridge-event"


def _normalize(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _normalize(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


@dataclass(slots=True)
class BridgeEnvelope:
    kind: str
    id: str = ""
    method: str = ""
    event: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    ok: bool = True
    result: dict[str, Any] | list[Any] | None = None
    error: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    version: int = BRIDGE_PROTOCOL_VERSION

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)


@dataclass(slots=True)
class BridgeJobSnapshot:
    id: str
    command: str
    status: str
    error: str | None = None
    result: dict[str, Any] | None = None
    updated_at_ms: int = 0
    repo_id: str = ""
    project_dir: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)


@dataclass(slots=True)
class BridgeEvent:
    event: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)
