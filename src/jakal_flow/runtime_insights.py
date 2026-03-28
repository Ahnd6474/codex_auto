from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean
from typing import Any

from .model_constants import BILLING_MODE_INCLUDED, BILLING_MODE_PER_PASS, BILLING_MODE_TOKEN
from .model_providers import normalize_billing_mode
from .models import ExecutionPlanState, ProjectContext, RuntimeOptions
from .parallel_resources import build_parallel_resource_plan
from .utils import read_jsonl_tail

UTC = getattr(datetime, "UTC", timezone.utc)


EFFORT_DURATION_BASELINES_SECONDS: dict[str, float] = {
    "low": 300.0,
    "medium": 540.0,
    "high": 840.0,
    "xhigh": 1_200.0,
}

EFFORT_USAGE_BASELINES: dict[str, dict[str, int]] = {
    "low": {
        "input_tokens": 6_000,
        "cached_input_tokens": 0,
        "output_tokens": 2_400,
        "reasoning_output_tokens": 600,
        "total_tokens": 9_000,
    },
    "medium": {
        "input_tokens": 11_000,
        "cached_input_tokens": 0,
        "output_tokens": 4_500,
        "reasoning_output_tokens": 1_500,
        "total_tokens": 17_000,
    },
    "high": {
        "input_tokens": 17_000,
        "cached_input_tokens": 0,
        "output_tokens": 6_500,
        "reasoning_output_tokens": 3_500,
        "total_tokens": 27_000,
    },
    "xhigh": {
        "input_tokens": 24_000,
        "cached_input_tokens": 0,
        "output_tokens": 8_500,
        "reasoning_output_tokens": 5_500,
        "total_tokens": 38_000,
    },
}


def _parse_iso_timestamp(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _duration_from_iso(started_at: str | None, completed_at: str | None) -> float | None:
    started = _parse_iso_timestamp(started_at)
    completed = _parse_iso_timestamp(completed_at)
    if started is None or completed is None:
        return None
    return max(0.0, round((completed - started).total_seconds(), 3))


def _elapsed_since(started_at: str | None) -> float:
    started = _parse_iso_timestamp(started_at)
    if started is None:
        return 0.0
    return max(0.0, round((datetime.now(tz=UTC) - started).total_seconds(), 3))


def _average(values: list[float]) -> float | None:
    filtered = [value for value in values if value > 0]
    if not filtered:
        return None
    return round(float(mean(filtered)), 3)


def _usage_baseline(effort: str) -> dict[str, int]:
    baseline = EFFORT_USAGE_BASELINES.get(str(effort or "").strip().lower(), EFFORT_USAGE_BASELINES["medium"])
    return dict(baseline)


def _duration_baseline(effort: str) -> float:
    return float(EFFORT_DURATION_BASELINES_SECONDS.get(str(effort or "").strip().lower(), EFFORT_DURATION_BASELINES_SECONDS["medium"]))


def estimate_usage_cost(
    usage: dict[str, int] | None,
    runtime: RuntimeOptions,
    *,
    pass_count: int = 0,
) -> dict[str, Any]:
    usage_payload = usage or {}
    billing_mode = normalize_billing_mode(getattr(runtime, "billing_mode", ""), getattr(runtime, "model_provider", "openai"))
    input_tokens = max(0, int(usage_payload.get("input_tokens", 0) or 0))
    cached_input_tokens = max(0, int(usage_payload.get("cached_input_tokens", 0) or 0))
    output_tokens = max(0, int(usage_payload.get("output_tokens", 0) or 0))
    reasoning_output_tokens = max(0, int(usage_payload.get("reasoning_output_tokens", 0) or 0))
    total_tokens = max(0, int(usage_payload.get("total_tokens", 0) or 0))
    if total_tokens <= 0:
        total_tokens = input_tokens + output_tokens + reasoning_output_tokens

    configured = False
    estimated_cost_usd = 0.0
    details: dict[str, float] = {}

    if billing_mode == BILLING_MODE_TOKEN:
        input_rate = max(0.0, float(getattr(runtime, "input_cost_per_million_usd", 0.0) or 0.0))
        cached_rate = max(0.0, float(getattr(runtime, "cached_input_cost_per_million_usd", 0.0) or 0.0))
        output_rate = max(0.0, float(getattr(runtime, "output_cost_per_million_usd", 0.0) or 0.0))
        reasoning_rate = max(0.0, float(getattr(runtime, "reasoning_output_cost_per_million_usd", 0.0) or 0.0))
        configured = any(rate > 0 for rate in [input_rate, cached_rate, output_rate, reasoning_rate])
        details = {
            "input_cost_usd": round((input_tokens / 1_000_000.0) * input_rate, 6),
            "cached_input_cost_usd": round((cached_input_tokens / 1_000_000.0) * cached_rate, 6),
            "output_cost_usd": round((output_tokens / 1_000_000.0) * output_rate, 6),
            "reasoning_output_cost_usd": round((reasoning_output_tokens / 1_000_000.0) * reasoning_rate, 6),
        }
        estimated_cost_usd = round(sum(details.values()), 6)
    elif billing_mode == BILLING_MODE_PER_PASS:
        per_pass_cost = max(0.0, float(getattr(runtime, "per_pass_cost_usd", 0.0) or 0.0))
        configured = per_pass_cost > 0
        estimated_cost_usd = round(per_pass_cost * max(0, int(pass_count or 0)), 6)
        details = {
            "per_pass_cost_usd": round(per_pass_cost, 6),
            "estimated_pass_count": float(max(0, int(pass_count or 0))),
        }
    else:
        configured = True
        estimated_cost_usd = 0.0

    return {
        "billing_mode": billing_mode,
        "configured": configured,
        "estimated_cost_usd": estimated_cost_usd,
        "usage": {
            "input_tokens": input_tokens,
            "cached_input_tokens": cached_input_tokens,
            "output_tokens": output_tokens,
            "reasoning_output_tokens": reasoning_output_tokens,
            "total_tokens": total_tokens,
        },
        "details": details,
    }


def build_runtime_insights(
    context: ProjectContext,
    plan_state: ExecutionPlanState,
    recent_usage: dict[str, int] | None,
    *,
    recent_passes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    per_effort_history: dict[str, list[float]] = {key: [] for key in EFFORT_DURATION_BASELINES_SECONDS}
    overall_history: list[float] = []
    completed_steps = []
    running_steps = []
    pending_steps = []

    for step in plan_state.steps:
        actual_duration = _duration_from_iso(step.started_at, step.completed_at)
        if actual_duration is not None and actual_duration > 0:
            per_effort_history.setdefault(step.reasoning_effort or "medium", []).append(actual_duration)
            overall_history.append(actual_duration)
        if step.status == "completed":
            completed_steps.append(step)
        elif step.status == "running":
            running_steps.append(step)
        else:
            pending_steps.append(step)

    overall_average = _average(overall_history)
    elapsed_seconds = 0.0
    remaining_seconds = 0.0
    step_estimates: list[dict[str, Any]] = []
    remaining_usage = {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_output_tokens": 0,
        "total_tokens": 0,
    }

    for step in plan_state.steps:
        actual_duration = _duration_from_iso(step.started_at, step.completed_at)
        effort = str(step.reasoning_effort or context.runtime.effort or "medium").strip().lower() or "medium"
        history_average = _average(per_effort_history.get(effort, []))
        estimated_duration = actual_duration or history_average or overall_average or _duration_baseline(effort)
        estimate_source = "actual" if actual_duration is not None else "history" if history_average or overall_average else "heuristic"
        elapsed_for_step = 0.0
        remaining_for_step = 0.0
        usage_baseline = _usage_baseline(effort)

        if step.status == "completed":
            elapsed_for_step = actual_duration if actual_duration is not None else estimated_duration
        elif step.status == "running":
            elapsed_for_step = _elapsed_since(step.started_at)
            estimated_duration = max(estimated_duration, elapsed_for_step)
            remaining_for_step = max(0.0, round(estimated_duration - elapsed_for_step, 3))
            for key, value in usage_baseline.items():
                remaining_usage[key] += value
        else:
            remaining_for_step = estimated_duration
            for key, value in usage_baseline.items():
                remaining_usage[key] += value

        elapsed_seconds += elapsed_for_step
        remaining_seconds += remaining_for_step
        step_estimates.append(
            {
                "step_id": step.step_id,
                "status": step.status,
                "reasoning_effort": effort,
                "estimated_duration_seconds": round(estimated_duration, 3),
                "actual_duration_seconds": round(actual_duration, 3) if actual_duration is not None else None,
                "elapsed_seconds": round(elapsed_for_step, 3),
                "remaining_seconds": round(remaining_for_step, 3),
                "source": estimate_source,
            }
        )

    recent_usage_payload = recent_usage or {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_output_tokens": 0,
        "total_tokens": 0,
    }
    recent_passes = recent_passes if recent_passes is not None else read_jsonl_tail(context.paths.pass_log_file, 25)
    recent_cost = estimate_usage_cost(recent_usage_payload, context.runtime, pass_count=len(recent_passes))
    remaining_cost = estimate_usage_cost(remaining_usage, context.runtime, pass_count=len(running_steps) + len(pending_steps))
    parallel_plan = build_parallel_resource_plan(
        getattr(context.runtime, "parallel_worker_mode", "auto"),
        getattr(context.runtime, "parallel_workers", 0),
        getattr(context.runtime, "parallel_memory_per_worker_gib", 3),
    )

    effort_baselines = []
    for effort, duration in EFFORT_DURATION_BASELINES_SECONDS.items():
        usage = _usage_baseline(effort)
        cost = estimate_usage_cost(usage, context.runtime, pass_count=1)
        effort_baselines.append(
            {
                "effort": effort,
                "estimated_duration_seconds": round(duration, 3),
                "usage": usage,
                "cost": cost,
            }
        )

    return {
        "execution": {
            "completed_step_count": len(completed_steps),
            "running_step_count": len(running_steps),
            "pending_step_count": len(pending_steps),
            "elapsed_seconds": round(elapsed_seconds, 3),
            "remaining_seconds": round(remaining_seconds, 3),
            "estimated_total_seconds": round(elapsed_seconds + remaining_seconds, 3),
            "step_estimates": step_estimates,
            "effort_baselines": effort_baselines,
        },
        "cost": {
            "recent": recent_cost,
            "remaining": remaining_cost,
            "estimated_total_cost_usd": round(
                float(recent_cost.get("estimated_cost_usd", 0.0) or 0.0)
                + float(remaining_cost.get("estimated_cost_usd", 0.0) or 0.0),
                6,
            ),
            "recent_usage": recent_cost.get("usage", {}),
            "remaining_usage": remaining_cost.get("usage", {}),
        },
        "parallel": parallel_plan.to_dict(),
    }
