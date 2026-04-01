from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from pathlib import Path
import tomllib
from typing import Any, Mapping

from .errors import RuntimeConfigError
from .model_constants import AUTO_MODEL_SLUG, DEFAULT_LOCAL_MODEL_PROVIDER, DEFAULT_MODEL_PROVIDER
from .model_providers import (
    effective_local_model_provider,
    normalize_billing_mode,
    normalize_local_model_provider,
    normalize_model_provider,
    provider_preset,
    provider_supports_auto_model,
)
from .model_selection import (
    DEFAULT_MODEL_PRESET_ID,
    model_preset_by_id,
    normalize_model_preset_id,
    normalize_reasoning_effort,
)
from .models import RuntimeOptions
from .optimization import normalize_optimization_mode
from .parallel_resources import normalize_parallel_worker_mode
from .platform_defaults import default_codex_path
from .step_models import (
    CLAUDE_DEFAULT_MODEL,
    DEEPSEEK_DEFAULT_MODEL,
    GEMINI_DEFAULT_MODEL,
    GLM_DEFAULT_MODEL,
    KIMI_DEFAULT_MODEL,
    MINIMAX_DEFAULT_MODEL,
    QWEN_CODE_DEFAULT_MODEL,
)
from .utils import normalize_workflow_mode, parse_json_text, read_text


def coerce_positive_int(value: Any, default: int, minimum: int = 1) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(minimum, parsed)


def coerce_nonnegative_int(value: Any, default: int = 0) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(0, parsed)


def coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def coerce_nonnegative_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def coerce_positive_tenths_float(value: Any, default: float, minimum: float = 0.1) -> float:
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        return default
    quantized = parsed.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    minimum_decimal = Decimal(str(minimum))
    if quantized < minimum_decimal:
        quantized = minimum_decimal
    return float(quantized)


def coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def desktop_runtime_defaults() -> dict[str, Any]:
    return RuntimeOptions(
        approval_mode="never",
        sandbox_mode="danger-full-access",
        allow_push=True,
        auto_merge_pull_request=True,
        checkpoint_interval_blocks=1,
        require_checkpoint_approval=False,
        generate_word_report=False,
        use_fast_mode=True,
        max_blocks=5,
        workflow_mode="standard",
        ml_max_cycles=3,
        model="gpt-5.4",
        execution_model="gpt-5.4",
        model_preset="",
        model_slug_input="gpt-5.4",
        ensemble_openai_model="gpt-5.4",
        ensemble_gemini_model=GEMINI_DEFAULT_MODEL,
        ensemble_claude_model=CLAUDE_DEFAULT_MODEL,
    ).to_dict()


def _default_runtime_payload(defaults: Mapping[str, Any] | RuntimeOptions | None = None) -> dict[str, Any]:
    if isinstance(defaults, RuntimeOptions):
        return defaults.to_dict()
    if isinstance(defaults, Mapping):
        return dict(defaults)
    return RuntimeOptions().to_dict()


def normalize_runtime_payload(
    payload: Mapping[str, Any] | None,
    *,
    defaults: Mapping[str, Any] | RuntimeOptions | None = None,
    force_execution_mode: str | None = None,
) -> dict[str, Any]:
    source = dict(payload or {})
    if "use_fast_mode" not in source and "use_compact_planning" in source:
        source["use_fast_mode"] = source.get("use_compact_planning")
    default_values = _default_runtime_payload(defaults)
    merged = {**default_values, **source}
    merged["max_blocks"] = coerce_positive_int(
        merged.get("max_blocks", default_values.get("max_blocks", 1)),
        default=int(default_values.get("max_blocks", 1) or 1),
    )
    merged["no_progress_limit"] = coerce_positive_int(
        merged.get("no_progress_limit", default_values.get("no_progress_limit", 3)),
        default=int(default_values.get("no_progress_limit", 3) or 3),
    )
    merged["regression_limit"] = coerce_positive_int(
        merged.get("regression_limit", default_values.get("regression_limit", 3)),
        default=int(default_values.get("regression_limit", 3) or 3),
    )
    merged["empty_cycle_limit"] = coerce_positive_int(
        merged.get("empty_cycle_limit", default_values.get("empty_cycle_limit", 3)),
        default=int(default_values.get("empty_cycle_limit", 3) or 3),
    )
    merged["optimization_mode"] = normalize_optimization_mode(
        merged.get("optimization_mode", default_values.get("optimization_mode", "off"))
    )
    merged["optimization_large_file_lines"] = coerce_positive_int(
        merged.get("optimization_large_file_lines", default_values.get("optimization_large_file_lines", 350)),
        default=int(default_values.get("optimization_large_file_lines", 350) or 350),
        minimum=50,
    )
    merged["optimization_long_function_lines"] = coerce_positive_int(
        merged.get("optimization_long_function_lines", default_values.get("optimization_long_function_lines", 80)),
        default=int(default_values.get("optimization_long_function_lines", 80) or 80),
        minimum=25,
    )
    merged["optimization_duplicate_block_lines"] = coerce_positive_int(
        merged.get("optimization_duplicate_block_lines", default_values.get("optimization_duplicate_block_lines", 4)),
        default=int(default_values.get("optimization_duplicate_block_lines", 4) or 4),
        minimum=3,
    )
    merged["optimization_max_files"] = coerce_positive_int(
        merged.get("optimization_max_files", default_values.get("optimization_max_files", 3)),
        default=int(default_values.get("optimization_max_files", 3) or 3),
        minimum=1,
    )
    merged["checkpoint_interval_blocks"] = coerce_positive_int(
        merged.get("checkpoint_interval_blocks", default_values.get("checkpoint_interval_blocks", 2)),
        default=int(default_values.get("checkpoint_interval_blocks", 2) or 2),
    )
    raw_parallel_worker_mode = merged.get("parallel_worker_mode", "auto")
    if "parallel_worker_mode" not in source and "parallel_workers" in source:
        raw_parallel_worker_mode = "manual"
    merged["parallel_worker_mode"] = normalize_parallel_worker_mode(raw_parallel_worker_mode)
    merged["parallel_workers"] = (
        coerce_nonnegative_int(merged.get("parallel_workers", default_values.get("parallel_workers", 0)), default=int(default_values.get("parallel_workers", 0) or 0))
        if merged["parallel_worker_mode"] == "auto"
        else coerce_positive_int(merged.get("parallel_workers", default_values.get("parallel_workers", 2)), default=max(1, int(default_values.get("parallel_workers", 2) or 2)))
    )
    merged["parallel_memory_per_worker_gib"] = coerce_positive_tenths_float(
        merged.get("parallel_memory_per_worker_gib", default_values.get("parallel_memory_per_worker_gib", 3.0)),
        default=float(default_values.get("parallel_memory_per_worker_gib", 3.0) or 3.0),
    )
    merged["save_project_logs"] = coerce_bool(
        merged.get("save_project_logs", default_values.get("save_project_logs", False)),
        bool(default_values.get("save_project_logs", False)),
    )
    merged["ml_max_cycles"] = coerce_positive_int(
        merged.get("ml_max_cycles", default_values.get("ml_max_cycles", 3)),
        default=int(default_values.get("ml_max_cycles", 3) or 3),
    )
    merged["allow_push"] = coerce_bool(
        merged.get("allow_push", default_values.get("allow_push", False)),
        bool(default_values.get("allow_push", False)),
    )
    merged["auto_merge_pull_request"] = coerce_bool(
        merged.get("auto_merge_pull_request", default_values.get("auto_merge_pull_request", False)),
        bool(default_values.get("auto_merge_pull_request", False)),
    )
    merged["allow_background_queue"] = coerce_bool(
        merged.get("allow_background_queue", default_values.get("allow_background_queue", True)),
        bool(default_values.get("allow_background_queue", True)),
    )
    merged["background_queue_priority"] = coerce_int(
        merged.get("background_queue_priority", default_values.get("background_queue_priority", 0)),
        default=int(default_values.get("background_queue_priority", 0) or 0),
    )
    merged["require_checkpoint_approval"] = coerce_bool(
        merged.get("require_checkpoint_approval", default_values.get("require_checkpoint_approval", True)),
        bool(default_values.get("require_checkpoint_approval", True)),
    )
    merged["execution_mode"] = force_execution_mode or str(merged.get("execution_mode", default_values.get("execution_mode", "parallel"))).strip() or "parallel"
    merged["workflow_mode"] = normalize_workflow_mode(merged.get("workflow_mode", default_values.get("workflow_mode", "standard")))
    merged["test_cmd"] = str(merged.get("test_cmd", default_values.get("test_cmd", "python -m pytest"))).strip() or "python -m pytest"
    merged["model_provider"] = normalize_model_provider(
        str(merged.get("model_provider", DEFAULT_MODEL_PROVIDER)),
        fallback=DEFAULT_MODEL_PROVIDER,
    )
    raw_chat_model_provider = str(merged.get("chat_model_provider", "")).strip().lower()
    merged["chat_model_provider"] = (
        normalize_model_provider(raw_chat_model_provider, fallback=DEFAULT_MODEL_PROVIDER)
        if raw_chat_model_provider
        else ""
    )
    provider = provider_preset(merged["model_provider"])
    merged["local_model_provider"] = normalize_local_model_provider(
        str(merged.get("local_model_provider", "")),
        fallback="",
    )
    merged["local_model_provider"] = effective_local_model_provider(
        merged["model_provider"],
        merged["local_model_provider"],
        fallback=DEFAULT_LOCAL_MODEL_PROVIDER,
    )
    merged["chat_local_model_provider"] = (
        normalize_local_model_provider(
            str(merged.get("chat_local_model_provider", "")),
            fallback="",
        )
        if merged["chat_model_provider"] in {"oss", "ollama"}
        else ""
    )
    merged["provider_base_url"] = str(merged.get("provider_base_url", "")).strip()
    if not merged["provider_base_url"] and provider.default_base_url:
        merged["provider_base_url"] = provider.default_base_url
    merged["provider_api_key_env"] = str(merged.get("provider_api_key_env", "")).strip()
    if not merged["provider_api_key_env"] and provider.default_api_key_env:
        merged["provider_api_key_env"] = provider.default_api_key_env
    merged["ensemble_openai_model"] = str(merged.get("ensemble_openai_model", "")).strip().lower() or "gpt-5.4"
    merged["ensemble_gemini_model"] = str(merged.get("ensemble_gemini_model", "")).strip().lower() or GEMINI_DEFAULT_MODEL
    merged["ensemble_claude_model"] = str(merged.get("ensemble_claude_model", "")).strip().lower() or CLAUDE_DEFAULT_MODEL
    if merged["model_provider"] == "ensemble":
        primary_ensemble_model = str(source.get("model", source.get("model_slug_input", ""))).strip().lower()
        merged["ensemble_openai_model"] = merged["ensemble_openai_model"] or primary_ensemble_model or "gpt-5.4"
    merged["billing_mode"] = normalize_billing_mode(
        str(merged.get("billing_mode", "")),
        merged["model_provider"],
        fallback=provider.default_billing_mode,
    )
    merged["input_cost_per_million_usd"] = coerce_nonnegative_float(merged.get("input_cost_per_million_usd", 0.0))
    merged["cached_input_cost_per_million_usd"] = coerce_nonnegative_float(merged.get("cached_input_cost_per_million_usd", 0.0))
    merged["output_cost_per_million_usd"] = coerce_nonnegative_float(merged.get("output_cost_per_million_usd", 0.0))
    merged["reasoning_output_cost_per_million_usd"] = coerce_nonnegative_float(
        merged.get("reasoning_output_cost_per_million_usd", 0.0)
    )
    merged["per_pass_cost_usd"] = coerce_nonnegative_float(merged.get("per_pass_cost_usd", 0.0))
    merged["codex_path"] = (
        str(merged.get("codex_path", "")).strip()
        or str(default_values.get("codex_path", "")).strip()
        or default_codex_path(merged["model_provider"])
    )
    merged["model"] = str(merged.get("model", "")).strip().lower()
    merged["chat_model"] = str(merged.get("chat_model", "")).strip().lower()
    merged["model_preset"] = normalize_model_preset_id(str(merged.get("model_preset", "")), fallback="")
    merged["effort_selection_mode"] = str(merged.get("effort_selection_mode", "")).strip().lower()
    if merged["effort_selection_mode"] not in {"auto", "explicit"}:
        merged["effort_selection_mode"] = "explicit"
    merged["use_fast_mode"] = coerce_bool(
        merged.get("use_fast_mode", default_values.get("use_fast_mode", False)),
        bool(default_values.get("use_fast_mode", False)),
    )
    merged["generate_word_report"] = coerce_bool(
        merged.get("generate_word_report", default_values.get("generate_word_report", False)),
        bool(default_values.get("generate_word_report", False)),
    )
    merged["effort"] = normalize_reasoning_effort(str(merged.get("effort", "")).strip(), fallback="medium")
    merged["planning_effort"] = normalize_reasoning_effort(
        str(merged.get("planning_effort", "")),
        fallback=merged["effort"],
    )

    provider_default_model = ""
    if merged["model_provider"] == "gemini":
        provider_default_model = GEMINI_DEFAULT_MODEL
    elif merged["model_provider"] == "claude":
        provider_default_model = CLAUDE_DEFAULT_MODEL
    elif merged["model_provider"] == "qwen_code":
        provider_default_model = QWEN_CODE_DEFAULT_MODEL
    elif merged["model_provider"] == "deepseek":
        provider_default_model = DEEPSEEK_DEFAULT_MODEL
    elif merged["model_provider"] == "kimi":
        provider_default_model = KIMI_DEFAULT_MODEL
    elif merged["model_provider"] == "minimax":
        provider_default_model = MINIMAX_DEFAULT_MODEL
    elif merged["model_provider"] == "glm":
        provider_default_model = GLM_DEFAULT_MODEL
    elif merged["model_provider"] == "ensemble":
        provider_default_model = merged["ensemble_openai_model"] or "gpt-5.4"
    if provider_default_model and "model" not in source and "model_slug_input" not in source:
        merged["model"] = provider_default_model
        merged["model_slug_input"] = provider_default_model

    if not merged["model"]:
        preset = model_preset_by_id(merged["model_preset"] or DEFAULT_MODEL_PRESET_ID)
        merged["model"] = preset.model if provider_supports_auto_model(merged["model_provider"]) else ""
    preset = model_preset_by_id(merged["model_preset"] or DEFAULT_MODEL_PRESET_ID)
    if not str(merged.get("effort", "")).strip():
        merged["effort"] = preset.effort
    merged["effort"] = normalize_reasoning_effort(merged["effort"], fallback=preset.effort)
    if not provider_supports_auto_model(merged["model_provider"]) and merged["model"] == AUTO_MODEL_SLUG:
        merged["model"] = ""
    if provider_supports_auto_model(merged["model_provider"]) and merged["model"] == AUTO_MODEL_SLUG:
        if merged["model_preset"]:
            merged["effort"] = model_preset_by_id(merged["model_preset"]).effort
        else:
            merged["model_preset"] = "auto" if merged["effort"] == "medium" else merged["effort"]
        if merged["model_preset"] == "auto":
            merged["effort_selection_mode"] = "auto"
        elif merged["effort_selection_mode"] == "auto":
            merged["effort_selection_mode"] = "explicit"
    elif merged["model_preset"]:
        merged["model_preset"] = ""
    merged["model_selection_mode"] = str(merged.get("model_selection_mode", "slug")).strip() or "slug"
    merged["model_slug_input"] = str(merged.get("model_slug_input", merged["model"])).strip().lower() or merged["model"]
    if provider_default_model and "model" not in source and "model_slug_input" not in source:
        merged["model_slug_input"] = provider_default_model
    if "model" not in source and str(source.get("model_slug_input", "")).strip():
        merged["model"] = merged["model_slug_input"]
    if not merged["model"] and merged["model_slug_input"]:
        merged["model"] = merged["model_slug_input"]
    merged["execution_model"] = str(source.get("execution_model", merged.get("execution_model", ""))).strip().lower()
    if "execution_model" not in source:
        merged["execution_model"] = merged["model"] or merged["model_slug_input"] or merged["execution_model"]
    if not merged["execution_model"]:
        merged["execution_model"] = merged["model"] or merged["model_slug_input"] or ""
    if merged["execution_model"]:
        merged["model"] = merged["execution_model"]
        merged["model_slug_input"] = merged["execution_model"]
    if merged["chat_model_provider"] and not provider_supports_auto_model(merged["chat_model_provider"]) and merged["chat_model"] == AUTO_MODEL_SLUG:
        merged["chat_model"] = ""
    return merged


def runtime_from_payload(
    payload: Mapping[str, Any] | None,
    *,
    defaults: Mapping[str, Any] | RuntimeOptions | None = None,
    force_execution_mode: str | None = None,
) -> RuntimeOptions:
    normalized = normalize_runtime_payload(
        payload,
        defaults=defaults,
        force_execution_mode=force_execution_mode,
    )
    return RuntimeOptions.from_dict(normalized)


def load_runtime_config_file(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    raw_text = read_text(path).strip()
    if not raw_text:
        return {}
    try:
        if suffix == ".toml":
            payload = tomllib.loads(raw_text)
        else:
            payload = parse_json_text(raw_text)
    except (json.JSONDecodeError, tomllib.TOMLDecodeError, TypeError, ValueError) as exc:
        raise RuntimeConfigError(f"Invalid runtime config file: {path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeConfigError(f"Runtime config must deserialize to an object: {path}")
    runtime_payload = payload.get("runtime", payload)
    if not isinstance(runtime_payload, dict):
        raise RuntimeConfigError(f"Runtime config payload must be an object: {path}")
    return runtime_payload


def parse_runtime_override(raw_item: str) -> tuple[str, Any]:
    text = str(raw_item or "").strip()
    if "=" not in text:
        raise RuntimeConfigError(f"Runtime override must use key=value syntax: {raw_item}")
    key, raw_value = text.split("=", 1)
    normalized_key = key.strip()
    if not normalized_key:
        raise RuntimeConfigError(f"Runtime override key is missing: {raw_item}")
    value_text = raw_value.strip()
    if not value_text:
        return normalized_key, ""
    try:
        parsed_value = parse_json_text(value_text)
    except (json.JSONDecodeError, TypeError, ValueError):
        parsed_value = value_text
    return normalized_key, parsed_value


def parse_runtime_overrides(values: list[str] | None) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for raw_item in values or []:
        key, value = parse_runtime_override(raw_item)
        overrides[key] = value
    return overrides


def load_runtime_from_sources(
    *,
    config_path: Path | None = None,
    config_payload: Mapping[str, Any] | None = None,
    overrides: Mapping[str, Any] | None = None,
    defaults: Mapping[str, Any] | RuntimeOptions | None = None,
    force_execution_mode: str | None = None,
) -> RuntimeOptions:
    merged: dict[str, Any] = {}
    if config_path is not None:
        merged.update(load_runtime_config_file(config_path))
    if config_payload:
        merged.update(dict(config_payload))
    if overrides:
        merged.update(dict(overrides))
    return runtime_from_payload(
        merged,
        defaults=defaults,
        force_execution_mode=force_execution_mode,
    )
