from __future__ import annotations

from dataclasses import dataclass

from .codex_app_server import AUTO_MODEL_SLUG
from .models import RuntimeOptions

MODEL_MODE_SLUG = "slug"
MODEL_MODE_CODEX = "codex"
VALID_MODEL_MODES = {MODEL_MODE_SLUG, MODEL_MODE_CODEX}
VALID_REASONING_EFFORTS = {"low", "medium", "high", "xhigh"}
DEFAULT_MODEL_SLUG = AUTO_MODEL_SLUG
DEFAULT_CODEX_BASE_SLUG = "gpt-5.4"
DEFAULT_CODEX_VARIANT_SLUG = "codex"


@dataclass(frozen=True, slots=True)
class ModelPreset:
    preset_id: str
    label: str
    model: str
    effort: str
    description: str

    def summary(self) -> str:
        return f"{self.label} | {self.model} | reasoning {self.effort}"


MODEL_PRESETS: tuple[ModelPreset, ...] = (
    ModelPreset(
        preset_id="auto",
        label="Auto",
        model=AUTO_MODEL_SLUG,
        effort="medium",
        description="Use Codex automatic model routing with the default reasoning balance.",
    ),
    ModelPreset(
        preset_id="auto-low",
        label="Auto / Low",
        model=AUTO_MODEL_SLUG,
        effort="low",
        description="Use automatic routing with lighter reasoning for faster edits and checks.",
    ),
    ModelPreset(
        preset_id="auto-medium",
        label="Auto / Medium",
        model=AUTO_MODEL_SLUG,
        effort="medium",
        description="Use automatic routing with balanced reasoning for everyday coding work.",
    ),
    ModelPreset(
        preset_id="auto-high",
        label="Auto / High",
        model=AUTO_MODEL_SLUG,
        effort="high",
        description="Use automatic routing with stronger reasoning for larger or trickier changes.",
    ),
    ModelPreset(
        preset_id="auto-xhigh",
        label="Auto / XHigh",
        model=AUTO_MODEL_SLUG,
        effort="xhigh",
        description="Use automatic routing with the deepest reasoning for the hardest investigations.",
    ),
)
DEFAULT_MODEL_PRESET_ID = "auto"


def normalize_model_mode(value: str, fallback: str = MODEL_MODE_SLUG) -> str:
    mode = value.strip().lower()
    if mode in VALID_MODEL_MODES:
        return mode
    return fallback


def normalize_reasoning_effort(value: str, fallback: str = "medium") -> str:
    effort = value.strip().lower()
    if effort in VALID_REASONING_EFFORTS:
        return effort
    return fallback


def validate_reasoning_effort(value: str) -> str:
    effort = value.strip().lower()
    if effort not in VALID_REASONING_EFFORTS:
        raise ValueError("Reasoning effort must be one of low, medium, high, xhigh.")
    return effort


def model_preset_by_id(preset_id: str, fallback: str = DEFAULT_MODEL_PRESET_ID) -> ModelPreset:
    requested = preset_id.strip().lower()
    for preset in MODEL_PRESETS:
        if preset.preset_id == requested:
            return preset
    for preset in MODEL_PRESETS:
        if preset.preset_id == fallback:
            return preset
    return MODEL_PRESETS[0]


def model_preset_from_runtime(runtime: RuntimeOptions) -> ModelPreset | None:
    if runtime.model_preset.strip():
        explicit = model_preset_by_id(runtime.model_preset, fallback="")
        if explicit.preset_id == runtime.model_preset.strip().lower():
            return explicit
    model = runtime.model.strip().lower()
    effort = normalize_reasoning_effort(runtime.effort)
    for preset in MODEL_PRESETS:
        if preset.model.lower() == model and preset.effort == effort:
            return preset
    for preset in MODEL_PRESETS:
        if preset.model.lower() == model:
            return preset
    return None


def join_slug_parts(*parts: str) -> str:
    cleaned: list[str] = []
    for part in parts:
        piece = str(part).strip().strip("-")
        if piece:
            cleaned.append(piece)
    return "-".join(cleaned)


def split_codex_slug(model: str) -> tuple[str, str]:
    raw = model.strip()
    if not raw:
        return DEFAULT_CODEX_BASE_SLUG, DEFAULT_CODEX_VARIANT_SLUG
    lowered = raw.lower()
    if lowered == "codex":
        return "", "codex"
    if "-codex" in lowered:
        index = lowered.index("-codex")
        base = raw[:index].strip().strip("-")
        variant = raw[index + 1 :].strip().strip("-")
        return base, variant or DEFAULT_CODEX_VARIANT_SLUG
    if lowered.startswith("codex-"):
        prefix, separator, suffix = raw.rpartition("-")
        if separator and prefix and suffix:
            return prefix.strip().strip("-"), suffix.strip().strip("-")
        return "", raw.strip().strip("-")
    return DEFAULT_CODEX_BASE_SLUG, DEFAULT_CODEX_VARIANT_SLUG


@dataclass(slots=True)
class ModelSelection:
    mode: str = MODEL_MODE_SLUG
    direct_slug: str = DEFAULT_MODEL_SLUG
    codex_base_slug: str = DEFAULT_CODEX_BASE_SLUG
    codex_variant_slug: str = DEFAULT_CODEX_VARIANT_SLUG
    effort: str = "medium"

    def normalized_mode(self) -> str:
        return normalize_model_mode(self.mode)

    def normalized_effort(self) -> str:
        return validate_reasoning_effort(self.effort)

    def resolved_slug(self) -> str:
        if self.normalized_mode() == MODEL_MODE_CODEX:
            resolved = join_slug_parts(self.codex_base_slug, self.codex_variant_slug)
        else:
            resolved = self.direct_slug.strip()
        if not resolved:
            raise ValueError("Model slug cannot be empty.")
        return resolved

    def summary(self) -> str:
        mode_label = "Codex builder" if self.normalized_mode() == MODEL_MODE_CODEX else "Direct slug"
        return f"Model {self.resolved_slug()} | {mode_label} | reasoning {self.normalized_effort()}"


def model_selection_from_runtime(runtime: RuntimeOptions) -> ModelSelection:
    inferred_mode = MODEL_MODE_CODEX if "codex" in runtime.model.lower() else MODEL_MODE_SLUG
    stored_mode = runtime.model_selection_mode.strip().lower()
    has_explicit_builder_inputs = any(
        [
            runtime.model_slug_input.strip(),
            runtime.codex_base_slug.strip(),
            runtime.codex_variant_slug.strip(),
        ]
    )
    if stored_mode in VALID_MODEL_MODES:
        mode = stored_mode
        if stored_mode == MODEL_MODE_SLUG and inferred_mode == MODEL_MODE_CODEX and not has_explicit_builder_inputs:
            mode = inferred_mode
    else:
        mode = inferred_mode
    direct_slug = runtime.model_slug_input.strip() or runtime.model.strip() or DEFAULT_MODEL_SLUG
    codex_base_slug = runtime.codex_base_slug.strip()
    codex_variant_slug = runtime.codex_variant_slug.strip()
    if not codex_base_slug and not codex_variant_slug:
        codex_base_slug, codex_variant_slug = split_codex_slug(runtime.model)
    return ModelSelection(
        mode=mode,
        direct_slug=direct_slug,
        codex_base_slug=codex_base_slug or DEFAULT_CODEX_BASE_SLUG,
        codex_variant_slug=codex_variant_slug or DEFAULT_CODEX_VARIANT_SLUG,
        effort=normalize_reasoning_effort(runtime.effort),
    )
