from __future__ import annotations

from dataclasses import dataclass
import re

from .model_constants import VALID_MODEL_PROVIDERS
from .models import ExecutionStep, RuntimeOptions

GEMINI_DEFAULT_MODEL = "gemini-3-flash"

_UI_PATH_PREFIXES = (
    "desktop/",
    "frontend/",
    "ui/",
    "web/",
    "website/",
)
_UI_SUFFIXES = (".css", ".scss", ".sass", ".less", ".jsx", ".tsx", ".html")
_UI_KEYWORD_PATTERN = re.compile(
    r"\b("
    r"ui|ux|frontend|react|tauri|desktop|screen|layout|style|styling|theme|component|"
    r"button|sidebar|toolbar|panel|modal|dialog|form|page|view"
    r")\b",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class StepModelChoice:
    provider: str
    model: str
    source: str
    reason: str


def normalize_step_model_provider(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in VALID_MODEL_PROVIDERS:
        return normalized
    return ""


def normalize_step_model(value: str) -> str:
    return str(value or "").strip().lower()


def resolve_step_model_choice(step: ExecutionStep, runtime: RuntimeOptions) -> StepModelChoice:
    explicit_provider = normalize_step_model_provider(getattr(step, "model_provider", ""))
    explicit_model = normalize_step_model(getattr(step, "model", ""))
    if explicit_provider:
        return StepModelChoice(
            provider=explicit_provider,
            model=explicit_model or _default_model_for_provider(explicit_provider, runtime),
            source="manual",
            reason="step override",
        )

    inferred_provider = "gemini" if _looks_like_ui_step(step) else "openai"
    reason = "AGENTS.md UI preference" if inferred_provider == "gemini" else "AGENTS.md Codex preference"
    return StepModelChoice(
        provider=inferred_provider,
        model=explicit_model or _default_model_for_provider(inferred_provider, runtime),
        source="auto",
        reason=reason,
    )


def _default_model_for_provider(provider: str, runtime: RuntimeOptions) -> str:
    normalized_provider = normalize_step_model_provider(provider) or "openai"
    runtime_provider = str(getattr(runtime, "model_provider", "") or "").strip().lower()
    runtime_model = normalize_step_model(getattr(runtime, "model", "") or getattr(runtime, "model_slug_input", ""))
    if normalized_provider == "gemini":
        if runtime_provider == "gemini" and runtime_model:
            return runtime_model
        return GEMINI_DEFAULT_MODEL
    if normalized_provider == "openai":
        return runtime_model or "auto"
    if runtime_provider == normalized_provider and runtime_model:
        return runtime_model
    return ""


def _looks_like_ui_step(step: ExecutionStep) -> bool:
    for raw_path in getattr(step, "owned_paths", []) or []:
        normalized_path = str(raw_path or "").strip().replace("\\", "/").lower()
        if not normalized_path:
            continue
        if normalized_path.startswith(_UI_PATH_PREFIXES):
            return True
        if normalized_path.startswith("desktop/") or normalized_path.endswith(_UI_SUFFIXES):
            return True
    text = " ".join(
        [
            str(getattr(step, "title", "") or ""),
            str(getattr(step, "display_description", "") or ""),
            str(getattr(step, "codex_description", "") or ""),
        ]
    )
    return bool(_UI_KEYWORD_PATTERN.search(text))
