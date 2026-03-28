from __future__ import annotations

AUTO_MODEL_SLUG = "auto"
VALID_REASONING_EFFORTS = {"low", "medium", "high", "xhigh"}
DEFAULT_MODEL_PROVIDER = "openai"
VALID_MODEL_PROVIDERS = {
    DEFAULT_MODEL_PROVIDER,
    "ensemble",
    "claude",
    "gemini",
    "openrouter",
    "opencdk",
    "local_openai",
    "oss",
}
DEFAULT_LOCAL_MODEL_PROVIDER = "ollama"
VALID_LOCAL_MODEL_PROVIDERS = {DEFAULT_LOCAL_MODEL_PROVIDER, "lmstudio"}
BILLING_MODE_INCLUDED = "included"
BILLING_MODE_TOKEN = "token"
BILLING_MODE_PER_PASS = "per_pass"
VALID_BILLING_MODES = {
    BILLING_MODE_INCLUDED,
    BILLING_MODE_TOKEN,
    BILLING_MODE_PER_PASS,
}
