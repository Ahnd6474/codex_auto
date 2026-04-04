from __future__ import annotations

from dataclasses import dataclass
import os
import shutil
import textwrap

from .models import ExecutionPlanState, ExecutionStep
from .planning import resolve_execution_flow_steps


_STATUS_LABELS = {
    "completed": ("O", "done", "green"),
    "running": (">", "running", "cyan"),
    "integrating": (">", "integrating", "cyan"),
    "failed": ("x", "failed", "red"),
    "paused": ("!", "paused", "yellow"),
    "awaiting_review": ("?", "review", "magenta"),
    "awaiting_checkpoint_approval": ("?", "checkpoint", "magenta"),
    "pending": (".", "pending", "white"),
    "not_started": (".", "pending", "white"),
}
_COLOR_CODES = {
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "magenta": "35",
    "cyan": "36",
    "white": "37",
}
_STEP_FIELD_ALIASES = {
    "title": "title",
    "desc": "display_description",
    "description": "display_description",
    "codex": "codex_description",
    "test": "test_command",
    "success": "success_criteria",
    "provider": "model_provider",
    "model": "model",
    "effort": "reasoning_effort",
    "status": "status",
    "deps": "depends_on",
    "depends": "depends_on",
    "group": "parallel_group",
    "paths": "owned_paths",
    "notes": "notes",
}
_CLOSEOUT_FIELD_ALIASES = {
    "title": "closeout_title",
    "desc": "closeout_display_description",
    "description": "closeout_display_description",
    "codex": "closeout_codex_description",
    "success": "closeout_success_criteria",
    "provider": "closeout_model_provider",
    "model": "closeout_model",
    "effort": "closeout_reasoning_effort",
    "status": "closeout_status",
    "paths": "closeout_owned_paths",
    "notes": "closeout_notes",
}


@dataclass(frozen=True, slots=True)
class FlowEditResult:
    plan_state: ExecutionPlanState
    message: str
    changed: bool = False


def supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    term = str(os.environ.get("TERM", "")).strip().lower()
    return bool(term) and term != "dumb"


def _style(text: str, *, color: str = "", bold: bool = False, dim: bool = False, enabled: bool = True) -> str:
    if not enabled:
        return text
    codes: list[str] = []
    if bold:
        codes.append("1")
    if dim:
        codes.append("2")
    if color:
        codes.append(_COLOR_CODES.get(color, ""))
    codes = [code for code in codes if code]
    if not codes:
        return text
    return f"\x1b[{';'.join(codes)}m{text}\x1b[0m"


def _terminal_width(default: int = 100) -> int:
    return max(72, int(shutil.get_terminal_size((default, 24)).columns))


def _status_parts(status: str) -> tuple[str, str, str]:
    normalized = str(status or "").strip().lower() or "pending"
    return _STATUS_LABELS.get(normalized, (".", normalized, "white"))


def _chip(step: ExecutionStep, *, use_color: bool) -> str:
    marker, label, color = _status_parts(step.status)
    title = step.title.strip() or "Untitled step"
    text = f"{marker} {step.step_id} {title} [{label}]"
    return _style(text, color=color, enabled=use_color)


def _closeout_chip(plan_state: ExecutionPlanState, *, use_color: bool) -> str:
    marker, label, color = _status_parts(plan_state.closeout_status)
    title = plan_state.closeout_title.strip() or "Closeout"
    return _style(f"{marker} CLOSEOUT {title} [{label}]", color=color, enabled=use_color)


def _execution_levels(steps: list[ExecutionStep]) -> list[list[ExecutionStep]]:
    if not steps:
        return []
    pending_by_id = {step.step_id: step for step in steps}
    resolved_ids: set[str] = set()
    levels: list[list[ExecutionStep]] = []
    while pending_by_id:
        ready = [
            step
            for step in pending_by_id.values()
            if all(dep in resolved_ids or dep not in pending_by_id for dep in step.depends_on)
        ]
        if not ready:
            ready = [pending_by_id[key] for key in sorted(pending_by_id)]
        ready.sort(key=lambda item: item.step_id)
        levels.append(ready)
        for step in ready:
            resolved_ids.add(step.step_id)
            pending_by_id.pop(step.step_id, None)
    return levels


def _wrap_flow_line(prefix: str, content: str, *, width: int) -> list[str]:
    wrapped = textwrap.wrap(
        content,
        width=max(20, width - len(prefix)),
        break_long_words=False,
        break_on_hyphens=False,
    )
    if not wrapped:
        return [prefix.rstrip()]
    return [f"{prefix}{wrapped[0]}", *[(" " * len(prefix)) + item for item in wrapped[1:]]]


def render_ascii_flow(
    plan_state: ExecutionPlanState,
    *,
    block_entries: list[dict] | None = None,
    use_color: bool | None = None,
) -> str:
    color_enabled = supports_color() if use_color is None else bool(use_color)
    resolved_steps = resolve_execution_flow_steps(plan_state.steps, block_entries)
    levels = _execution_levels(resolved_steps)
    completed_count = sum(1 for step in resolved_steps if str(step.status).strip().lower() == "completed")
    width = _terminal_width()
    title = plan_state.plan_title.strip() or "Untitled execution flow"
    header = _style("jakal-flow execution board", color="cyan", bold=True, enabled=color_enabled)
    meta = (
        f"title={title}  workflow={plan_state.workflow_mode or 'standard'}  "
        f"mode={plan_state.execution_mode or 'parallel'}  steps={completed_count}/{len(resolved_steps)}"
    )
    legend = "Legend: O done  > running  ! paused  x failed  ? review  . pending"
    lines = [header, meta, legend, ""]
    if not resolved_steps:
        lines.append("START")
        lines.append("  `-- no execution steps yet; use /plan or $add")
        lines.append("")
        lines.append(_closeout_chip(plan_state, use_color=color_enabled))
        return "\n".join(lines)

    lines.append("START")
    for index, level in enumerate(levels, start=1):
        prefix = "  +-- " if index < len(levels) else "  `-- "
        joined = " || ".join(_chip(step, use_color=color_enabled) for step in level)
        lines.extend(_wrap_flow_line(prefix, joined, width=width))
    lines.append("      |")
    lines.extend(_wrap_flow_line("      `-- ", _closeout_chip(plan_state, use_color=color_enabled), width=width))
    return "\n".join(lines)


def render_plan_table(plan_state: ExecutionPlanState) -> str:
    if not plan_state.steps:
        return "No execution steps saved."
    lines = []
    for step in plan_state.steps:
        deps = ",".join(step.depends_on) or "-"
        lines.append(
            f"{step.step_id:<4} status={step.status or 'pending':<12} deps={deps:<10} "
            f"provider={step.model_provider or '-':<10} model={step.model or '-':<20} title={step.title}"
        )
    return "\n".join(lines)


def _parse_edit_value(raw_value: str) -> str:
    value = str(raw_value or "").strip()
    if not value:
        raise ValueError("A value is required after '::'.")
    return value


def _split_key_value(raw_text: str) -> tuple[str, str]:
    if "::" not in raw_text:
        raise ValueError("Expected '::' to separate the field and the new value.")
    left, right = raw_text.split("::", 1)
    return left.strip(), _parse_edit_value(right)


def _split_list(value: str) -> list[str]:
    items = [item.strip() for item in value.replace("\n", ",").split(",")]
    return [item for item in items if item]


def _resolve_step(plan_state: ExecutionPlanState, selector: str) -> tuple[int, ExecutionStep]:
    normalized = str(selector or "").strip()
    if not normalized:
        raise ValueError("A step selector is required.")
    if normalized.isdigit():
        index = int(normalized) - 1
        if 0 <= index < len(plan_state.steps):
            return index, plan_state.steps[index]
    for index, step in enumerate(plan_state.steps):
        if step.step_id == normalized:
            return index, step
    raise ValueError(f"Unknown step selector: {selector}")


def _set_step_field(step: ExecutionStep, field_name: str, value: str) -> None:
    normalized = _STEP_FIELD_ALIASES.get(field_name.strip().lower())
    if normalized is None:
        raise ValueError(f"Unsupported step field: {field_name}")
    if normalized in {"depends_on", "owned_paths"}:
        setattr(step, normalized, _split_list(value))
        return
    if normalized in {"model_provider", "model", "reasoning_effort", "status"}:
        setattr(step, normalized, value.strip().lower())
        return
    setattr(step, normalized, value)
    if normalized == "display_description" and not step.codex_description.strip():
        step.codex_description = value


def _set_closeout_field(plan_state: ExecutionPlanState, field_name: str, value: str) -> None:
    normalized = _CLOSEOUT_FIELD_ALIASES.get(field_name.strip().lower())
    if normalized is None:
        raise ValueError(f"Unsupported closeout field: {field_name}")
    if normalized in {"closeout_owned_paths"}:
        setattr(plan_state, normalized, _split_list(value))
        return
    if normalized in {"closeout_model_provider", "closeout_model", "closeout_reasoning_effort", "closeout_status"}:
        setattr(plan_state, normalized, value.strip().lower())
        return
    setattr(plan_state, normalized, value)
    if normalized == "closeout_display_description" and not plan_state.closeout_codex_description.strip():
        plan_state.closeout_codex_description = value


def apply_flow_edit(plan_state: ExecutionPlanState, raw_command: str) -> FlowEditResult:
    command_text = str(raw_command or "").strip()
    if not command_text:
        return FlowEditResult(plan_state=plan_state, message="No flow command supplied.", changed=False)
    parts = command_text.split(maxsplit=1)
    action = parts[0].strip().lower()
    rest = parts[1].strip() if len(parts) > 1 else ""

    if action in {"show", "flow"}:
        return FlowEditResult(plan_state=plan_state, message="Flow refreshed.", changed=False)
    if action == "list":
        return FlowEditResult(plan_state=plan_state, message="Plan listing refreshed.", changed=False)
    if action == "add":
        title, description = _split_key_value(rest) if "::" in rest else (rest.strip(), rest.strip())
        if not title:
            raise ValueError("A step title is required.")
        next_index = len(plan_state.steps) + 1
        plan_state.steps.append(
            ExecutionStep(
                step_id=f"TMP{next_index}",
                title=title,
                display_description=description,
                codex_description=description,
                test_command=plan_state.default_test_command,
                status="pending",
            )
        )
        return FlowEditResult(plan_state=plan_state, message=f"Added step TMP{next_index}.", changed=True)
    if action == "drop":
        index, step = _resolve_step(plan_state, rest)
        plan_state.steps.pop(index)
        return FlowEditResult(plan_state=plan_state, message=f"Dropped {step.step_id}.", changed=True)
    if action == "swap":
        left_raw, right_raw = rest.split(maxsplit=1)
        left_index, left = _resolve_step(plan_state, left_raw)
        right_index, right = _resolve_step(plan_state, right_raw)
        plan_state.steps[left_index], plan_state.steps[right_index] = plan_state.steps[right_index], plan_state.steps[left_index]
        return FlowEditResult(plan_state=plan_state, message=f"Swapped {left.step_id} and {right.step_id}.", changed=True)
    if action == "set":
        selector, remainder = rest.split(maxsplit=1)
        field_name, value = _split_key_value(remainder)
        _index, step = _resolve_step(plan_state, selector)
        _set_step_field(step, field_name, value)
        return FlowEditResult(plan_state=plan_state, message=f"Updated {step.step_id} {field_name}.", changed=True)
    if action == "closeout":
        field_name, value = _split_key_value(rest)
        _set_closeout_field(plan_state, field_name, value)
        return FlowEditResult(plan_state=plan_state, message=f"Updated closeout {field_name}.", changed=True)
    raise ValueError(f"Unsupported flow command: {action}")
