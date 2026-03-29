import { Suspense, lazy, useEffect } from "react";
import { useI18n } from "../../i18n";

/* ── Tab icons ── */
function RunTabIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <polygon
        points="5 3 19 12 5 21 5 3"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="currentColor"
        fillOpacity="0.15"
      />
    </svg>
  );
}

function ConfigTabIcon() {
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

function DashboardTabIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3" y="3" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

function HistoryTabIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="7.25" stroke="currentColor" strokeWidth="1.7" />
      <path d="M12 8v4.5l3 1.75" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ReportsTabIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinejoin="round"
      />
      <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

const TAB_ICONS = {
  run: <RunTabIcon />,
  config: <ConfigTabIcon />,
  dashboard: <DashboardTabIcon />,
  history: <HistoryTabIcon />,
  reports: <ReportsTabIcon />,
};

/* ── Lazy view loader ── */
function createLazyNamedView(loader, exportName) {
  let loadedComponent = null;
  let pendingModule = null;

  function load() {
    if (!pendingModule) {
      pendingModule = loader().then((module) => {
        loadedComponent = module[exportName];
        return { default: module[exportName] };
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
      <div className="empty-block" style={{ marginTop: "40px" }}>
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" style={{ animation: "skeleton-pulse 1.2s ease-in-out infinite" }}>
          <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.8" strokeDasharray="4 4" />
        </svg>
        <span style={{ color: "var(--text-dim)", fontSize: "13px" }}>Loading view…</span>
      </div>
    </section>
  );
}

function WorkspaceTab({ value, activeTab, onChange, onPrefetch, label }) {
  const icon = TAB_ICONS[value] || null;
  return (
    <button
      className={`workspace-tab ${activeTab === value ? "active" : ""}`}
      onClick={() => onChange(value)}
      onMouseEnter={() => onPrefetch?.(value)}
      onFocus={() => onPrefetch?.(value)}
      type="button"
    >
      {icon}
      {label}
    </button>
  );
}

export function CenterWorkspace({
  activeTab,
  onChangeTab,
  detail,
  workspaceShareDetail,
  historyDetail,
  selectedHistoryId,
  form,
  shareSettings,
  autoRunAfterPlan,
  programSettings,
  planDraft,
  selectedStepId,
  modelPresets,
  modelCatalog,
  busy,
  canRequestStop,
  canCancelReservation,
  shareBusy,
  queuedJobs,
  onChangeForm,
  onChangeProgramSettings,
  onSaveProject,
  onSaveProgramSettings,
  programSettingsDirty = false,
  onChooseDirectory,
  onArchiveProject,
  onDeleteProject,
  onDeleteHistoryEntry,
  onGenerateShareLink,
  onCopyShareLink,
  onRevokeShareLink,
  onChangeShareSettings,
  onChangeAutoRunAfterPlan,
  onPromptChange,
  onGeneratePlan,
  onSavePlan,
  onResetPlan,
  onRunPlan,
  onRunManualDebugger,
  onRunManualMerger,
  onRequestStop,
  onCancelQueuedJob,
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
  const visibleHistoryDetail = selectedHistoryId ? historyDetail : detail;

  function resolveTabView(tab) {
    switch (tab) {
      case "run": return ParallelRunControlView;
      case "dashboard": return DashboardView;
      case "reports": return developerMode ? ReportsView : null;
      case "history": return HistoryView;
      case "config": return ConfigEditorView;
      case "app-settings": return AppSettingsView;
      default: return null;
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
  }, [activeTab, developerMode]);

  useEffect(() => {
    if (!developerMode && activeTab === "reports") {
      onChangeTab("run");
    }
  }, [activeTab, developerMode, onChangeTab]);

  const visibleTabs = [
    ["run", t("tab.flow")],
    ["config", t("tab.config")],
    ["dashboard", t("tab.dashboard")],
    ["history", t("tab.history")],
    ...(developerMode ? [["reports", t("tab.reports")]] : []),
  ];

  return (
    <section className="workspace-area">
      <div className="workspace-tabs">
        {visibleTabs.map(([value, label]) => (
          <WorkspaceTab
            key={value}
            value={value}
            activeTab={activeTab}
            onChange={onChangeTab}
            onPrefetch={preloadTab}
            label={label}
          />
        ))}
      </div>

      <Suspense fallback={<ViewLoadingFallback />}>
        {activeTab === "run" ? (
          <ParallelRunControlView
            detail={detail}
            codexStatus={detail?.codex_status}
            planDraft={planDraft}
            activeJob={activeJob}
            shareSettings={shareSettings}
            autoRunAfterPlan={autoRunAfterPlan}
            selectedStepId={selectedStepId}
            form={form}
            busy={busy}
            canRequestStop={canRequestStop}
            canCancelReservation={canCancelReservation}
            queuedJobs={queuedJobs}
            onPromptChange={onPromptChange}
            onChangeForm={onChangeForm}
            onGeneratePlan={onGeneratePlan}
            onSavePlan={onSavePlan}
            onResetPlan={onResetPlan}
            onRunPlan={onRunPlan}
            onRunManualDebugger={onRunManualDebugger}
            onRunManualMerger={onRunManualMerger}
            onRequestStop={onRequestStop}
            onCancelQueuedJob={onCancelQueuedJob}
            onGenerateShareLink={onGenerateShareLink}
            onCopyShareLink={onCopyShareLink}
            onRevokeShareLink={onRevokeShareLink}
            onChangeShareSettings={onChangeShareSettings}
            onAutoRunAfterPlanChange={onChangeAutoRunAfterPlan}
            onSelectStep={onSelectStep}
            onUpdateStepField={onUpdateStepField}
            onSaveStepLocal={onSaveStepLocal}
            onAddStep={onAddStep}
            onDeleteStep={onDeleteStep}
          />
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
        {activeTab === "history" ? (
          <HistoryView detail={visibleHistoryDetail} busy={busy} onDeleteHistoryEntry={onDeleteHistoryEntry} />
        ) : null}
        {activeTab === "config" ? (
          <ConfigEditorView
            form={form}
            modelPresets={modelPresets}
            modelCatalog={modelCatalog}
            codexStatus={detail?.codex_status}
            busy={busy}
            activeJob={activeJob}
            onChangeForm={onChangeForm}
            onChangeProgramSettings={onChangeProgramSettings}
            onSaveProject={onSaveProject}
            onChooseDirectory={onChooseDirectory}
            onArchiveProject={onArchiveProject}
            onDeleteProject={onDeleteProject}
          />
        ) : null}
        {activeTab === "app-settings" ? (
          <AppSettingsView
            settings={programSettings}
            codexStatus={detail?.codex_status}
            shareSettings={shareSettings}
            shareDetail={workspaceShareDetail}
            busy={busy}
            shareBusy={shareBusy}
            dirty={programSettingsDirty}
            onChangeSettings={onChangeProgramSettings}
            onSaveSettings={onSaveProgramSettings}
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
