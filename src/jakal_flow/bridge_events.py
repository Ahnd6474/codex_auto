from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, Protocol


class BridgeEventSink(Protocol):
    def emit(self, event: str, payload: dict[str, Any] | None = None) -> None:
        ...


_sink_var: ContextVar[BridgeEventSink | None] = ContextVar("jakal_flow_bridge_event_sink", default=None)


@contextmanager
def bridge_event_context(sink: BridgeEventSink | None) -> Iterator[None]:
    token = _sink_var.set(sink)
    try:
        yield
    finally:
        _sink_var.reset(token)


def emit_bridge_event(event: str, payload: dict[str, Any] | None = None) -> None:
    sink = _sink_var.get()
    if sink is None:
        return
    sink.emit(event, payload or {})
