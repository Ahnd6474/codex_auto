import { useI18n } from "../../i18n";
import {
  applyConfigRuntimeModelSelection,
  filterModelCatalogByProvider,
  MODEL_PROVIDER_OPTIONS,
  normalizedModelProvider,
  providerSupportsCatalog,
  REASONING_OPTIONS,
  runtimeSummary,
  selectedConfigReasoning,
} from "../../utils";

const PROVIDER_LABELS = {
  openai: "OpenAI / Codex",
  claude: "Anthropic Claude",
  gemini: "Google Gemini",
  ensemble: "Ensemble",
  openrouter: "OpenRouter",
  local_openai: "Local (OpenAI-compat)",
  deepseek: "DeepSeek",
  qwen_code: "Qwen Code",
  kimi: "Kimi",
  minimax: "MiniMax",
  glm: "GLM",
  opencdk: "OpenCDK",
  oss: "OSS",
};

const EFFORT_LABELS = {
  low: "Low",
  medium: "Medium",
  high: "High",
  xhigh: "X-High",
};

export function ModelPane({ form, modelPresets, modelCatalog, onChangeForm, onHide }) {
  const { t } = useI18n();
  const runtime = form?.runtime || {};
  const selectedProvider = normalizedModelProvider(runtime);
  const scopedModelCatalog = filterModelCatalogByProvider(modelCatalog, runtime);
  const providerHasCatalog = providerSupportsCatalog(selectedProvider);
  const selectedModel = runtime.model || "";
  const selectedEffort = selectedConfigReasoning(scopedModelCatalog, runtime) || "medium";
  const visibleModels = (scopedModelCatalog || []).filter((item) => item && item.model && !item.hidden);

  function applyModelChange(nextModel) {
    if (!form) return;
    const nextRuntime = applyConfigRuntimeModelSelection(runtime, scopedModelCatalog, nextModel, null);
    onChangeForm((current) => ({ ...current, runtime: nextRuntime }));
  }

  function applyRuntimePatch(patch) {
    if (!form) return;
    onChangeForm((current) => ({ ...current, runtime: { ...(current.runtime || {}), ...patch } }));
  }

  return (
    <aside className="details-pane">
      <div
        className="tool-window__header"
        style={{ margin: "-8px -8px 0", padding: "0 6px", borderBottom: "1px solid var(--border)" }}
      >
        <div className="tool-tabs">
          <span className="tool-tab active">Model</span>
        </div>
        {onHide ? (
          <div className="tool-window__header-actions">
            <button
              className="tool-window__header-btn"
              onClick={onHide}
              type="button"
              title={`${t("action.dismiss")} (Alt+R)`}
              aria-label="Hide model panel"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
        ) : null}
      </div>

      {!form ? (
        <p className="model-pane__empty">프로젝트를 선택하면 모델 설정을 변경할 수 있습니다.</p>
      ) : (
        <div className="model-pane__body">
          <div className="model-pane__section">
            <label className="model-pane__label">Provider</label>
            <select
              value={selectedProvider}
              onChange={(e) => applyRuntimePatch({ model_provider: e.target.value, model: "" })}
            >
              {MODEL_PROVIDER_OPTIONS.map((p) => (
                <option key={p} value={p}>{PROVIDER_LABELS[p] || p}</option>
              ))}
            </select>
          </div>

          {providerHasCatalog && visibleModels.length > 0 ? (
            <div className="model-pane__section">
              <label className="model-pane__label">Model</label>
              <select
                value={selectedModel}
                onChange={(e) => applyModelChange(e.target.value)}
              >
                {visibleModels.map((item) => (
                  <option key={item.model} value={item.model}>{item.display_name || item.model}</option>
                ))}
              </select>
            </div>
          ) : null}

          <div className="model-pane__section">
            <label className="model-pane__label">Reasoning Effort</label>
            <select
              value={selectedEffort}
              onChange={(e) => applyRuntimePatch({ effort: e.target.value })}
            >
              {REASONING_OPTIONS.map((opt) => (
                <option key={opt} value={opt}>{EFFORT_LABELS[opt] || opt}</option>
              ))}
            </select>
          </div>

          <div className="model-pane__summary">
            <span className="model-pane__summary-label">현재 설정</span>
            <span className="model-pane__summary-value">{runtimeSummary(runtime, modelPresets)}</span>
          </div>
        </div>
      )}
    </aside>
  );
}
