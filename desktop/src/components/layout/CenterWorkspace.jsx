import { Suspense, lazy, useEffect } from "react";
import { useI18n } from "../../i18n";

function createLazyNamedView(loader, exportName) {
  let loadedComponent = null;
  let pendingModule = null;

  function load() {
    if (!pendingModule) {
      pendingModule = loader().then((module) => {
        loadedComponent = module[exportName];
        return {
          default: module[exportName],
        };
      });
    }
    return pendingModule;
  }

  const LazyComponent = lazy(load);

  function PreloadableView(props) {
    if (loadedComponent) {
      const Component = loadedComponent;
      return <Component {...props} />;
    }
    return <LazyComponent {...props} />;
  }

  PreloadableView.preload = load;
  return PreloadableView;
}

const DashboardView = createLazyNamedView(() => import("../views/DashboardView"), "DashboardView");
const ParallelRunControlView = createLazyNamedView(() => import("../views/ParallelRunControlView"), "ParallelRunControlView");
const RunControlView = createLazyNamedView(() => import("../views/RunControlView"), "RunControlView");
const ReportsView = createLazyNamedView(() => import("../views/ReportsView"), "ReportsView");
const HistoryView = createLazyNamedView(() => import("../views/HistoryView"), "HistoryView");
const ConfigEditorView = createLazyNamedView(() => import("../views/ConfigEditorView"), "ConfigEditorView");
const AppSettingsView = createLazyNamedView(() => import("../views/AppSettingsView"), "AppSettingsView");

function scheduleIdlePrefetch(callback) {
  if (typeof window !== "undefined" && typeof window.requestIdleCallback === "function") {
    const handle = window.requestIdleCallback(callback, { timeout: 400 });
    return () => window.cancelIdleCallback(handle);
  }
  if (typeof window !== "undefined") {
    const handle = window.setTimeout(callback, 120);
    return () => window.clearTimeout(handle);
  }
  return () => {};
}

function ViewLoadingFallback() {
  return (
    <section className="workspace-view" aria-busy="true">
      <div className="empty-block">Loading view...</div>
    </section>
  );
}

function WorkspaceTab({ value, activeTab, onChange, onPrefetch, label }) {
  return (
    <button
      className={`workspace-tab ${activeTab === value ? "active" : ""}`}
      onClick={() => onChange(value)}
      onMouseEnter={() => onPrefetch?.(value)}
      onFocus={() => onPrefetch?.(value)}
      type="button"
    >
      {label}
    </button>
  );
}

export function CenterWorkspace({
  activeTab,
  onChangeTab,
  detail,
  form,
  shareSettings,
  programSettings,
  planDraft,
  selectedStepId,
  modelPresets,
  modelCatalog,
  busy,
  onChangeForm,
  onChangeProgramSettings,
  onChooseDirectory,
  onDeleteProject,
  onGenerateShareLink,
  onCopyShareLink,
  onRevokeShareLink,
  onChangeShareSettings,
  onPromptChange,
  onGeneratePlan,
  onSavePlan,
  onResetPlan,
  onRunPlan,
  onRunCloseout,
  onRequestStop,
  onSelectStep,
  onUpdateStepField,
  onSaveStepLocal,
  onAddStep,
  onDeleteStep,
  onMoveStep,
  activeJob,
}) {
  const { t } = useI18n();
  const developerMode = Boolean(programSettings?.developer_mode);
  const executionMode = String(form?.runtime?.execution_mode || planDraft?.execution_mode || detail?.runtime?.execution_mode || "serial")
    .trim()
    .toLowerCase();

  function resolveTabView(tab) {
    switch (tab) {
      case "run":
        return executionMode === "parallel" ? ParallelRunControlView : RunControlView;
      case "dashboard":
        return DashboardView;
      case "reports":
        return developerMode ? ReportsView : null;
      case "history":
        return developerMode ? HistoryView : null;
      case "config":
        return ConfigEditorView;
      case "app-settings":
        return AppSettingsView;
      default:
        return null;
    }
  }

  function preloadTab(tab) {
    const ViewComponent = resolveTabView(tab);
    ViewComponent?.preload?.();
  }

  useEffect(() => {
    preloadTab(activeTab);
    const likelyNextTabs =
      activeTab === "run"
        ? ["config", "dashboard"]
        : activeTab === "config"
          ? ["run", "dashboard"]
          : activeTab === "dashboard"
            ? ["run", "config"]
            : activeTab === "reports"
              ? ["history", "dashboard"]
              : activeTab === "history"
                ? ["reports", "dashboard"]
                : ["config"];
    return scheduleIdlePrefetch(() => {
      likelyNextTabs.forEach((tab) => preloadTab(tab));
    });
  }, [activeTab, developerMode, executionMode]);

  useEffect(() => {
    if (!developerMode && (activeTab === "reports" || activeTab === "history")) {
      onChangeTab("run");
    }
  }, [activeTab, developerMode, onChangeTab]);

  const visibleTabs = [
    ["run", t("tab.flow")],
    ["config", t("tab.config")],
    ["dashboard", t("tab.dashboard")],
    ...(developerMode
      ? [
          ["reports", t("tab.reports")],
          ["history", t("tab.history")],
        ]
      : []),
  ];

  return (
    <section className="workspace-area">
      <div className="workspace-tabs">
        {visibleTabs.map(([value, label]) => (
          <WorkspaceTab key={value} value={value} activeTab={activeTab} onChange={onChangeTab} onPrefetch={preloadTab} label={label} />
        ))}
      </div>

      <Suspense fallback={<ViewLoadingFallback />}>
        {activeTab === "run" ? (
          executionMode === "parallel" ? (
            <ParallelRunControlView
              detail={detail}
              planDraft={planDraft}
              shareSettings={shareSettings}
              selectedStepId={selectedStepId}
              busy={busy}
              onPromptChange={onPromptChange}
              onGeneratePlan={onGeneratePlan}
              onSavePlan={onSavePlan}
              onResetPlan={onResetPlan}
              onRunPlan={onRunPlan}
              onRunCloseout={onRunCloseout}
              onRequestStop={onRequestStop}
              onGenerateShareLink={onGenerateShareLink}
              onCopyShareLink={onCopyShareLink}
              onRevokeShareLink={onRevokeShareLink}
              onChangeShareSettings={onChangeShareSettings}
              onSelectStep={onSelectStep}
              onUpdateStepField={onUpdateStepField}
              onSaveStepLocal={onSaveStepLocal}
              onAddStep={onAddStep}
              onDeleteStep={onDeleteStep}
            />
          ) : (
            <RunControlView
              detail={detail}
              planDraft={planDraft}
              shareSettings={shareSettings}
              selectedStepId={selectedStepId}
              busy={busy}
              onPromptChange={onPromptChange}
              onGeneratePlan={onGeneratePlan}
              onSavePlan={onSavePlan}
              onResetPlan={onResetPlan}
              onRunPlan={onRunPlan}
              onRunCloseout={onRunCloseout}
              onRequestStop={onRequestStop}
              onGenerateShareLink={onGenerateShareLink}
              onCopyShareLink={onCopyShareLink}
              onRevokeShareLink={onRevokeShareLink}
              onChangeShareSettings={onChangeShareSettings}
              onSelectStep={onSelectStep}
              onUpdateStepField={onUpdateStepField}
              onSaveStepLocal={onSaveStepLocal}
              onAddStep={onAddStep}
              onDeleteStep={onDeleteStep}
              onMoveStep={onMoveStep}
            />
          )
        ) : null}
        {activeTab === "dashboard" ? (
          <DashboardView
            detail={detail}
            planDraft={planDraft}
            form={form}
            programSettings={programSettings}
            busy={busy}
            modelPresets={modelPresets}
            modelCatalog={modelCatalog}
            activeJob={activeJob}
            onChangeForm={onChangeForm}
          />
        ) : null}
        {developerMode && activeTab === "reports" ? <ReportsView reports={detail?.reports} /> : null}
        {developerMode && activeTab === "history" ? <HistoryView history={detail?.history} /> : null}
        {activeTab === "config" ? (
          <ConfigEditorView
            form={form}
            modelPresets={modelPresets}
            modelCatalog={modelCatalog}
            busy={busy}
            onChangeForm={onChangeForm}
            onChooseDirectory={onChooseDirectory}
            onDeleteProject={onDeleteProject}
          />
        ) : null}
        {activeTab === "app-settings" ? (
          <AppSettingsView
            settings={programSettings}
            shareSettings={shareSettings}
            shareDetail={detail?.share}
            busy={busy}
            onChangeSettings={onChangeProgramSettings}
            onGenerateShareLink={onGenerateShareLink}
            onCopyShareLink={onCopyShareLink}
            onRevokeShareLink={onRevokeShareLink}
            onChangeShareSettings={onChangeShareSettings}
          />
        ) : null}
      </Suspense>
    </section>
  );
}
