from __future__ import annotations

from .model_providers import (
    discover_local_model_catalog,
    normalize_billing_mode,
    normalize_local_model_provider,
    provider_preset,
    provider_supports_auto_model,
)
from .models import RuntimeOptions
from .platform_defaults import default_codex_path
from .step_models import (
    CLAUDE_DEFAULT_MODEL,
    DEEPSEEK_DEFAULT_MODEL,
    GEMINI_DEFAULT_MODEL,
    GLM_DEFAULT_MODEL,
    KIMI_DEFAULT_MODEL,
    MINIMAX_DEFAULT_MODEL,
    QWEN_CODE_DEFAULT_MODEL,
    normalize_step_model,
    normalize_step_model_provider,
)

REMOTE_FALLBACK_PROVIDERS = (
    "openai",
    "claude",
    "gemini",
    "qwen_code",
    "deepseek",
    "kimi",
    "minimax",
    "glm",
    "openrouter",
    "opencdk",
)
LOCAL_FALLBACK_PROVIDERS = ("oss", "local_openai")

_QUOTA_ERROR_MARKERS = (
    "exhausted your capacity",
    "quota will reset",
    "quota window is exhausted",
    "rate limit",
    "resource exhausted",
    "too many requests",
    "no openai credits are available",
    "no credits are available",
)
_FALLBACKABLE_ERROR_MARKERS = _QUOTA_ERROR_MARKERS + (
    "please set an auth method",
    "authentication failed",
    "invalid api key",
    "unauthorized",
    "not authenticated",
    "login required",
    "not installed",
    "not reachable",
    "connection refused",
    "failed to connect",
    "timed out",
    "timeout",
    "no such host",
    "name or service not known",
    "error when talking to gemini api",
    "modelnotfounderror",
    "requested entity was not found",
    "requires at least one detected local model",
)


def is_quota_exhaustion_error(detail: str) -> bool:
    lowered = str(detail or "").strip().lower()
    if not lowered:
        return False
    return any(marker in lowered for marker in _QUOTA_ERROR_MARKERS)


def is_provider_fallbackable_error(detail: str) -> bool:
    lowered = str(detail or "").strip().lower()
    if not lowered:
        return False
    return any(marker in lowered for marker in _FALLBACKABLE_ERROR_MARKERS)


def build_provider_fallback_runtimes(
    runtime: RuntimeOptions,
    *,
    current_provider: str = "",
    local_models: list[dict[str, object]] | None = None,
) -> list[RuntimeOptions]:
    normalized_current = normalize_step_model_provider(current_provider or getattr(runtime, "model_provider", "")) or "openai"
    discovered_local_models = local_models if local_models is not None else discover_local_model_catalog()
    candidates: list[RuntimeOptions] = []
    seen: set[tuple[str, str, str, str, str]] = set()

    ordered_providers = [
        *[provider for provider in REMOTE_FALLBACK_PROVIDERS if provider != normalized_current],
        *[provider for provider in LOCAL_FALLBACK_PROVIDERS if provider != normalized_current],
    ]
    for provider in ordered_providers:
        candidate = _fallback_runtime_for_provider(runtime, provider, local_models=discovered_local_models)
        if candidate is None:
            continue
        key = (
            str(candidate.model_provider),
            str(candidate.local_model_provider),
            str(candidate.model),
            str(candidate.provider_base_url),
            str(candidate.provider_api_key_env),
        )
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)
    return candidates


def _fallback_runtime_for_provider(
    runtime: RuntimeOptions,
    provider: str,
    *,
    local_models: list[dict[str, object]],
) -> RuntimeOptions | None:
    normalized_provider = normalize_step_model_provider(provider)
    if not normalized_provider:
        return None

    payload = runtime.to_dict()
    payload.update(
        {
            "model_provider": normalized_provider,
            "provider_base_url": provider_preset(normalized_provider).default_base_url,
            "provider_api_key_env": provider_preset(normalized_provider).default_api_key_env,
            "billing_mode": normalize_billing_mode(
                "",
                normalized_provider,
                fallback=provider_preset(normalized_provider).default_billing_mode,
            ),
            "codex_path": default_codex_path(normalized_provider),
            "model_selection_mode": "slug",
        }
    )

    if normalized_provider == "oss":
        local_target = _select_local_oss_target(runtime, local_models)
        if local_target is None:
            return None
        local_provider, model = local_target
        payload.update(
            {
                "model_provider": "oss",
                "local_model_provider": local_provider,
                "provider_base_url": "",
                "provider_api_key_env": "",
                "codex_path": default_codex_path("openai"),
                "model": model,
                "model_slug_input": model,
                "model_preset": "",
                "effort_selection_mode": "explicit",
            }
        )
        return RuntimeOptions.from_dict(payload)

    if normalized_provider == "local_openai":
        payload.update(
            {
                "local_model_provider": "",
                "model": _default_model_for_provider(normalized_provider, runtime),
                "model_slug_input": _default_model_for_provider(normalized_provider, runtime),
                "model_preset": "",
                "effort_selection_mode": "explicit",
            }
        )
        return RuntimeOptions.from_dict(payload)

    model = _default_model_for_provider(normalized_provider, runtime)
    supports_auto = provider_supports_auto_model(normalized_provider)
    payload.update(
        {
            "local_model_provider": "",
            "model": model,
            "model_slug_input": model,
            "model_preset": "auto" if supports_auto and model == "auto" else "",
            "effort_selection_mode": "auto" if supports_auto and model == "auto" else "explicit",
        }
    )
    return RuntimeOptions.from_dict(payload)


def _default_model_for_provider(provider: str, runtime: RuntimeOptions) -> str:
    normalized_provider = normalize_step_model_provider(provider) or "openai"
    runtime_provider = normalize_step_model_provider(getattr(runtime, "model_provider", ""))
    runtime_model = normalize_step_model(
        getattr(runtime, "execution_model", "") or getattr(runtime, "model", "") or getattr(runtime, "model_slug_input", "")
    )
    ensemble_openai_model = normalize_step_model(getattr(runtime, "ensemble_openai_model", ""))
    ensemble_gemini_model = normalize_step_model(getattr(runtime, "ensemble_gemini_model", ""))
    ensemble_claude_model = normalize_step_model(getattr(runtime, "ensemble_claude_model", ""))

    if normalized_provider == "gemini":
        if runtime_provider == "ensemble" and ensemble_gemini_model:
            return ensemble_gemini_model
        if runtime_provider == "gemini" and runtime_model:
            return runtime_model
        return GEMINI_DEFAULT_MODEL
    if normalized_provider == "claude":
        if runtime_provider == "ensemble" and ensemble_claude_model:
            return ensemble_claude_model
        if runtime_provider == "claude" and runtime_model:
            return runtime_model
        return CLAUDE_DEFAULT_MODEL
    if normalized_provider == "qwen_code":
        if runtime_provider == "qwen_code" and runtime_model:
            return runtime_model
        return QWEN_CODE_DEFAULT_MODEL
    if normalized_provider == "deepseek":
        if runtime_provider == "deepseek" and runtime_model:
            return runtime_model
        return DEEPSEEK_DEFAULT_MODEL
    if normalized_provider == "kimi":
        if runtime_provider == "kimi" and runtime_model:
            return runtime_model
        return KIMI_DEFAULT_MODEL
    if normalized_provider == "minimax":
        if runtime_provider == "minimax" and runtime_model:
            return runtime_model
        return MINIMAX_DEFAULT_MODEL
    if normalized_provider == "glm":
        if runtime_provider == "glm" and runtime_model:
            return runtime_model
        return GLM_DEFAULT_MODEL
    if normalized_provider in {"openai", "ensemble", "openrouter", "opencdk", "local_openai"}:
        if runtime_provider == "ensemble" and ensemble_openai_model:
            return ensemble_openai_model
        if runtime_provider in {"openai", "ensemble"} and runtime_model:
            return runtime_model
        return "auto"
    return runtime_model or "auto"


def _select_local_oss_target(
    runtime: RuntimeOptions,
    local_models: list[dict[str, object]],
) -> tuple[str, str] | None:
    installed_models = [
        item
        for item in local_models
        if isinstance(item, dict)
        and str(item.get("provider", "")).strip().lower() == "oss"
        and bool(item.get("installed"))
    ]
    if not installed_models:
        return None

    preferred_local_provider = normalize_local_model_provider(
        getattr(runtime, "local_model_provider", ""),
        fallback="",
    )
    preferred_model = normalize_step_model(getattr(runtime, "model", "") or getattr(runtime, "model_slug_input", ""))

    for item in installed_models:
        local_provider = normalize_local_model_provider(str(item.get("local_provider", "")), fallback="")
        model = normalize_step_model(str(item.get("model", "")))
        if preferred_local_provider and preferred_local_provider == local_provider and preferred_model and preferred_model == model:
            return local_provider, model

    for item in installed_models:
        local_provider = normalize_local_model_provider(str(item.get("local_provider", "")), fallback="")
        model = normalize_step_model(str(item.get("model", "")))
        if preferred_local_provider and preferred_local_provider == local_provider and model:
            return local_provider, model

    default_local_provider = normalize_local_model_provider(getattr(runtime, "local_model_provider", ""), fallback="")
    if default_local_provider:
        for item in installed_models:
            local_provider = normalize_local_model_provider(str(item.get("local_provider", "")), fallback="")
            model = normalize_step_model(str(item.get("model", "")))
            if default_local_provider == local_provider and model:
                return local_provider, model

    first_item = installed_models[0]
    first_provider = normalize_local_model_provider(str(first_item.get("local_provider", "")), fallback="")
    first_model = normalize_step_model(str(first_item.get("model", "")))
    if not first_provider or not first_model:
        return None
    return first_provider, first_model
