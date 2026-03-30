import { memo, useMemo } from "react";
import { useI18n } from "../../i18n";
import {
  clampReasoningEffort,
  defaultModelForRuntime,
  filterModelCatalogByProvider,
  findModelCatalogEntry,
  normalizeMemoryBudgetGiB,
  normalizedModelProvider,
  REASONING_OPTIONS,
  reasoningEffortLabel,
} from "../../utils";

/* ── View header icon ── */
function ConfigHeaderIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"
        stroke="currentColor"
        strokeWidth="1.5"
      />
      <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

/* ── Toggle row ── */
function ToggleRow({ checked, onChange, disabled, label, hint }) {
  return (
    <label className="toggle-row">
      <span className="toggle-row__label">
        <span>{label}</span>
        {hint ? <small>{hint}</small> : null}
      </span>
      <span className={`toggle-track ${checked ? "toggle-track--on" : ""}`}>
        <input type="checkbox" checked={checked} onChange={onChange} disabled={disabled} />
        <span className="toggle-thumb" />
      </span>
    </label>
  );
}

/* ── Section icons ── */
function ProjectIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M4.75 7.25A2.5 2.5 0 0 1 7.25 4.75h5.1c.66 0 1.3.26 1.77.73l5.15 5.15c.47.47.73 1.1.73 1.77v4.35a2.5 2.5 0 0 1-2.5 2.5h-10a2.5 2.5 0 0 1-2.5-2.5v-9.5Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M13 4.9v5.35a1 1 0 0 0 1 1h5.1" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  );
}

function GithubIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ExecutionIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <polygon points="5 3 19 12 5 21 5 3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" fill="currentColor" fillOpacity="0.12" />
    </svg>
  );
}

function InfoIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.7" />
      <path d="M12 8v1M12 11v5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function FolderIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  );
}

function SectionHeader({ icon, title, description, trailing }) {
  return (
    <div className="section-header">
      <div className="section-header__icon">{icon}</div>
      <div className="section-header__text" style={{ flex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <strong>{title}</strong>
          {trailing}
        </div>
        {description ? <small>{description}</small> : null}
      </div>
    </div>
  );
}

function configEditorViewPropsEqual(previousProps, nextProps) {
  return (
    previousProps.form === nextProps.form
    && previousProps.modelPresets === nextProps.modelPresets
    && previousProps.modelCatalog === nextProps.modelCatalog
    && previousProps.codexStatus === nextProps.codexStatus
    && previousProps.busy === nextProps.busy
    && previousProps.activeJob === nextProps.activeJob
  );
}

export const ConfigEditorView = memo(function ConfigEditorView({
  form,
  modelPresets,
  modelCatalog,
  codexStatus,
  busy,
  activeJob,
  onChangeForm,
  onChangeProgramSettings,
  onSaveProject,
  onChooseDirectory,
  onArchiveProject,
  onDeleteProject,
}) {
  const runtime = form.runtime || {};
  const { language, t } = useI18n();
  const isRunning = ["running", "queued"].includes(String(activeJob?.status || "").trim().toLowerCase());
  const liveRuntimeEditable = isRunning;
  const planningReasoningLabel = language === "ko" ? "계획 추론" : "Planning Reasoning";
  const selectedProvider = normalizedModelProvider(runtime);
  const autoParallelWorkers = String(runtime.parallel_worker_mode || "auto").trim().toLowerCase() !== "manual";

  const planningRuntime =
    selectedProvider === "ensemble"
      ? {
          ...runtime,
          model_provider: "openai",
          model: runtime.ensemble_openai_model || runtime.model || defaultModelForRuntime(modelCatalog, { ...runtime, model_provider: "openai" }) || "auto",
          model_slug_input: runtime.ensemble_openai_model || runtime.model_slug_input || runtime.model || "",
        }
      : runtime;
  const planningCatalog = useMemo(
    () => filterModelCatalogByProvider(modelCatalog, planningRuntime),
    [modelCatalog, planningRuntime],
  );
  const planningModel = planningRuntime.model || planningRuntime.model_slug_input || defaultModelForRuntime(modelCatalog, planningRuntime) || runtime.model || "";
  const planningEntry = useMemo(
    () => findModelCatalogEntry(planningCatalog, planningModel),
    [planningCatalog, planningModel],
  );
  const planningSupportedEfforts = useMemo(
    () => (
      planningEntry?.supported_reasoning_efforts?.length
        ? planningEntry.supported_reasoning_efforts
        : REASONING_OPTIONS
    ).filter((effort) => REASONING_OPTIONS.includes(effort)),
    [planningEntry],
  );
  const planningSelectedEffort = useMemo(
    () => clampReasoningEffort(
      planningCatalog,
      planningModel,
      runtime.planning_effort || runtime.effort || "medium",
      runtime.effort || "medium",
    ),
    [planningCatalog, planningModel, runtime.effort, runtime.planning_effort],
  );

  return (
    <section className="workspace-view">
      <div className="view-header">
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <div className="view-header-icon">
            <ConfigHeaderIcon />
          </div>
          <div>
            <span className="eyebrow">{t("tab.config")}</span>
            <h2>{form.display_name || t("tab.config")}</h2>
          </div>
        </div>
        <div className="field-row">
          <button
            className="toolbar-button toolbar-button--accent"
            onClick={onSaveProject}
            type="button"
            disabled={(!liveRuntimeEditable && busy) || !form.project_dir?.trim()}
          >
            {t("action.saveConfiguration")}
          </button>
          <button
            className="toolbar-button toolbar-button--ghost"
            onClick={onArchiveProject}
            type="button"
            disabled={busy || !form.project_dir?.trim()}
          >
            {t("action.archiveProject")}
          </button>
          <button
            className="toolbar-button"
            onClick={onDeleteProject}
            type="button"
            disabled={busy || !form.project_dir?.trim() || isRunning}
            style={{ color: isRunning ? "var(--text-dim)" : "var(--danger)" }}
            title={isRunning ? (language === "ko" ? "실행 중인 프로젝트는 삭제할 수 없습니다." : "Cannot delete a running project.") : undefined}
          >
            {t("action.deleteProject")}
          </button>
        </div>
      </div>

      {/* Project info summary card */}
      {form.display_name || form.project_dir ? (
        <div className="project-summary-card">
          <div className="field">
            <span>{t("config.projectName")}</span>
            <strong>{form.display_name || "—"}</strong>
          </div>
          <div className="field">
            <span>{t("common.branch")}</span>
            <strong>{form.branch || "—"}</strong>
          </div>
          <div className="field" style={{ gridColumn: "1 / -1" }}>
            <span>{t("config.workingDirectory")}</span>
            <p style={{ fontFamily: "monospace", fontSize: "12px" }}>{form.project_dir || "—"}</p>
          </div>
        </div>
      ) : null}

      <div className="form-layout">
        {/* ── Left column — Project & Execution ── */}
        <div className="form-section">
          {/* Project basics */}
          <div className="subsection">
            <SectionHeader
              icon={<ProjectIcon />}
              title={language === "ko" ? "프로젝트 기본 설정" : "Project Basics"}
              description={language === "ko" ? "이름, 디렉터리, 브랜치" : "Project name, directory and branch"}
            />

            <label className="field" style={{ marginTop: "4px" }}>
              <span>{t("config.projectName")}</span>
              <input
                value={form.display_name}
                onChange={(event) => onChangeForm((current) => ({ ...current, display_name: event.target.value }))}
                disabled={busy}
              />
            </label>

            <label className="field field--wide">
              <span>{t("config.workingDirectory")}</span>
              <div className="field-row">
                <input
                  value={form.project_dir}
                  onChange={(event) => onChangeForm((current) => ({ ...current, project_dir: event.target.value }))}
                  disabled={busy}
                />
                <button className="toolbar-button" onClick={onChooseDirectory} type="button" disabled={busy} style={{ flexShrink: 0 }}>
                  <FolderIcon />
                  {t("action.browse")}
                </button>
              </div>
            </label>

            <label className="field">
              <span>{t("common.branch")}</span>
              <input
                value={form.branch}
                onChange={(event) => onChangeForm((current) => ({ ...current, branch: event.target.value }))}
                disabled={busy}
              />
            </label>
          </div>

          {/* Execution params */}
          <div className="subsection">
            <SectionHeader
              icon={<ExecutionIcon />}
              title={language === "ko" ? "실행 설정" : "Execution Parameters"}
              description={language === "ko" ? "단계 수, 병렬 실행, 최적화" : "Step limits, parallel workers and optimization"}
            />

            {liveRuntimeEditable ? (
              <div className="info-callout" style={{ marginTop: "8px" }}>
                <InfoIcon />
                <span>
                  {language === "ko"
                    ? "실행 중에도 체크포인트와 보고서처럼 안전한 런타임 설정은 저장해서 다음 단계부터 반영할 수 있습니다."
                    : "Safe runtime settings like checkpoints and report output can still be saved while a run is active."}
                </span>
              </div>
            ) : null}

            <div className="choice-grid" style={{ marginTop: "4px" }}>
              <label className="field">
                <span>{t("field.workflowMode")}</span>
                <select
                  value={runtime.workflow_mode || "standard"}
                  onChange={(event) =>
                    onChangeForm((current) => ({
                      ...current,
                      runtime: { ...current.runtime, workflow_mode: event.target.value },
                    }))
                  }
                  disabled={busy}
                >
                  <option value="standard">{t("option.workflowStandard")}</option>
                  <option value="ml">{t("option.workflowML")}</option>
                </select>
              </label>

              {/* Unified step limit: max steps for standard, ML cycles for ml mode */}
              {runtime.workflow_mode === "ml" ? (
                <label className="field">
                  <span>{t("field.mlMaxCycles")}</span>
                  <input
                    type="number"
                    min="1"
                    value={runtime.ml_max_cycles || 3}
                    onChange={(event) =>
                      onChangeForm((current) => ({
                        ...current,
                        runtime: { ...current.runtime, ml_max_cycles: Math.max(1, Number.parseInt(event.target.value || "1", 10) || 1) },
                      }))
                    }
                    disabled={busy}
                  />
                  <small style={{ fontSize: "11px", color: "var(--text-dim)" }}>
                    {language === "ko" ? "ML 실험 최대 반복 횟수" : "Max ML experiment iterations"}
                  </small>
                </label>
              ) : (
                <label className="field">
                  <span>{t("config.maxPlannedSteps")}</span>
                  <input
                    type="number"
                    min="1"
                    value={runtime.max_blocks || 5}
                    onChange={(event) =>
                      onChangeForm((current) => ({
                        ...current,
                        runtime: { ...current.runtime, max_blocks: Math.max(1, Number.parseInt(event.target.value || "1", 10) || 1) },
                      }))
                    }
                    disabled={busy}
                  />
                  <small style={{ fontSize: "11px", color: "var(--text-dim)" }}>
                    {language === "ko" ? "실행 계획의 최대 단계 수" : "Maximum steps in execution plan"}
                  </small>
                </label>
              )}

              <label className="field">
                <span>{planningReasoningLabel}</span>
                <select
                  value={planningSelectedEffort}
                  onChange={(event) =>
                    onChangeForm((current) => ({
                      ...current,
                      runtime: { ...current.runtime, planning_effort: event.target.value },
                    }))
                  }
                  disabled={busy}
                >
                  {planningSupportedEfforts.map((effort) => (
                    <option key={effort} value={effort}>{reasoningEffortLabel(effort, language)}</option>
                  ))}
                </select>
              </label>

              <label className="field">
                <span>{t("field.parallelWorkers")}</span>
                <input
                  type="number"
                  min="1"
                  value={runtime.parallel_workers > 0 ? runtime.parallel_workers : 4}
                  onChange={(event) =>
                    onChangeForm((current) => ({
                      ...current,
                      runtime: {
                        ...current.runtime,
                        parallel_workers: Math.max(1, Number.parseInt(event.target.value || "1", 10) || 1),
                      },
                    }))
                  }
                  disabled={busy || autoParallelWorkers}
                />
              </label>

              <label className="field">
                <span>{t("field.parallelMemoryPerWorkerGiB")}</span>
                <input
                  type="number"
                  min="0.1"
                  step="0.1"
                  value={runtime.parallel_memory_per_worker_gib || 3}
                  onChange={(event) =>
                    onChangeForm((current) => ({
                      ...current,
                      runtime: {
                        ...current.runtime,
                        parallel_memory_per_worker_gib: normalizeMemoryBudgetGiB(
                          event.target.value,
                          current.runtime?.parallel_memory_per_worker_gib || 3,
                        ),
                      },
                    }))
                  }
                  disabled={busy}
                />
              </label>

              <label className="field">
                <span>{t("field.checkpointInterval")}</span>
                <input
                  type="number"
                  min="1"
                  value={runtime.checkpoint_interval_blocks || 1}
                  onChange={(event) =>
                    onChangeForm((current) => ({
                      ...current,
                      runtime: {
                        ...current.runtime,
                        checkpoint_interval_blocks: Math.max(1, Number.parseInt(event.target.value || "1", 10) || 1),
                      },
                    }))
                  }
                  disabled={busy && !liveRuntimeEditable}
                />
              </label>

              <label className="field">
                <span>{t("field.optimizationMode")}</span>
                <select
                  value={runtime.optimization_mode || "light"}
                  onChange={(event) =>
                    onChangeForm((current) => ({
                      ...current,
                      runtime: { ...current.runtime, optimization_mode: event.target.value },
                    }))
                  }
                  disabled={busy}
                >
                  <option value="off">{t("option.optimizationOff")}</option>
                  <option value="light">{t("option.optimizationLight")}</option>
                  <option value="refactor">{t("option.optimizationRefactor")}</option>
                </select>
              </label>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "6px", marginTop: "4px" }}>
              <ToggleRow
                checked={autoParallelWorkers}
                onChange={(event) =>
                  onChangeForm((current) => ({
                    ...current,
                    runtime: {
                      ...current.runtime,
                      parallel_worker_mode: event.target.checked ? "auto" : "manual",
                      parallel_workers: event.target.checked
                        ? Math.max(0, Number.parseInt(String(current.runtime?.parallel_workers || "0"), 10) || 0)
                        : Math.max(1, Number.parseInt(String(current.runtime?.parallel_workers || "4"), 10) || 4),
                    },
                  }))
                }
                label={t("preset.auto")}
                hint={language === "ko" ? "병렬 작업자 수를 자동으로 결정" : "Automatically determine parallel worker count"}
                disabled={busy}
              />
              <ToggleRow
                checked={runtime.allow_background_queue ?? true}
                onChange={(event) =>
                  onChangeForm((current) => ({
                    ...current,
                    runtime: { ...current.runtime, allow_background_queue: event.target.checked },
                  }))
                }
                label={t("field.allowBackgroundQueue")}
                disabled={busy}
              />
              <ToggleRow
                checked={Boolean(runtime.require_checkpoint_approval)}
                onChange={(event) =>
                  onChangeForm((current) => ({
                    ...current,
                    runtime: { ...current.runtime, require_checkpoint_approval: event.target.checked },
                  }))
                }
                label={t("option.requireCheckpointApproval")}
                hint={language === "ko" ? "체크포인트에 도달하면 다음 단계 전에 검토를 요청합니다." : "Pause for review when a checkpoint is reached."}
                disabled={busy && !liveRuntimeEditable}
              />
              <ToggleRow
                checked={Boolean(runtime.use_fast_mode)}
                onChange={(event) =>
                  onChangeForm((current) => ({
                    ...current,
                    runtime: { ...current.runtime, use_fast_mode: event.target.checked },
                  }))
                }
                label={t("option.useFastMode")}
                hint={
                  language === "ko"
                    ? "계획 생성에서 Planner Agent A를 생략하고 압축 계획 경로를 사용합니다."
                    : "Skip Planner Agent A during plan generation and use the compact planning path."
                }
                disabled={busy}
              />
            </div>
          </div>
        </div>

        {/* ── Right column — GitHub + Model ── */}
        <div className="form-section">
          {/* GitHub */}
          <div className="subsection">
            <SectionHeader
              icon={<GithubIcon />}
              title={t("config.githubConnection")}
              description={language === "ko" ? "원격 저장소 연결 방식" : "How this project connects to a remote repository"}
            />
            <div style={{ display: "flex", flexDirection: "column", gap: "6px", marginTop: "4px" }}>
              {[
                ["existing", t("config.useExistingOrigin")],
                ["manual", t("config.manualGithubUrl")],
                ["none", t("config.noGithubYet")],
              ].map(([value, label]) => (
                <label key={value} className="toggle-row">
                  <span className="toggle-row__label"><span>{label}</span></span>
                  <input
                    type="radio"
                    checked={form.github_mode === value}
                    onChange={() => onChangeForm((current) => ({ ...current, github_mode: value }))}
                    disabled={busy}
                    style={{ width: "auto", border: "none", background: "none", padding: 0, accentColor: "var(--info)" }}
                  />
                </label>
              ))}
            </div>
            {form.github_mode === "manual" ? (
              <label className="field field--wide" style={{ marginTop: "8px" }}>
                <span>{t("config.githubUrl")}</span>
                <input
                  value={form.origin_url}
                  onChange={(event) => onChangeForm((current) => ({ ...current, origin_url: event.target.value }))}
                  disabled={busy}
                  placeholder="https://github.com/org/repo"
                />
              </label>
            ) : null}
          </div>

        </div>
      </div>
    </section>
  );
}, configEditorViewPropsEqual);

