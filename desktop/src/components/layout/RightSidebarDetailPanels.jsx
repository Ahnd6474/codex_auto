import { memo, useEffect, useMemo, useRef, useState } from "react";
import { openInSystem } from "../../api";
import { useI18n } from "../../i18n";
import { displayStatus } from "../../locale";
import { effectiveStepStatus, formatCheckpointDisplayId, projectStatusWithJob, reasoningEffortLabel, runtimeSummary, statusTone, visibleExecutionJob } from "../../utils";

function RailTerminalIcon() {
  return (
    <svg aria-hidden="true" className="sidebar-icon__svg" viewBox="0 0 24 24" fill="none">
      <rect x="2" y="4" width="20" height="16" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M6 9l4 3-4 3M13 15h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function OpenFolderIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" width="12" height="12">
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
      <polyline points="15 3 21 3 21 9" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
      <line x1="10" y1="14" x2="21" y2="3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function WordDocIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" width="20" height="20">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <polyline points="14 2 14 8 20 8" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M8 13l2 6 2-4 2 4 2-6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function PptDocIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" width="20" height="20">
      <rect x="2" y="4" width="20" height="14" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M8 18v2M16 18v2M6 20h12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M9 8h3a2 2 0 0 1 0 4H9V8z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
    </svg>
  );
}

function WebDocIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" width="20" height="20">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" />
      <path d="M2 12h20M12 3c-2.5 3-4 5.5-4 9s1.5 6 4 9M12 3c2.5 3 4 5.5 4 9s-1.5 6-4 9" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

function MarkdownDocIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" width="20" height="20">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <polyline points="14 2 14 8 20 8" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M8 13h8M8 17h6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

function OutputCard({ icon, title, description, enabled, checked, onChange, busy, allowWhileRunning = false, comingSoon, language }) {
  return (
    <div className={`output-card ${!enabled ? "output-card--disabled" : ""}`}>
      <div className="output-card__icon">{icon}</div>
      <div className="output-card__body">
        <div className="output-card__title">
          <strong>{title}</strong>
          {comingSoon ? (
            <span className="output-card__badge">{language === "ko" ? "Coming soon" : "Coming soon"}</span>
          ) : null}
        </div>
        <p className="output-card__desc">{description}</p>
      </div>
      <label className={`output-card__toggle ${!enabled ? "output-card__toggle--disabled" : ""}`}>
        <span className={`toggle-track ${checked ? "toggle-track--on" : ""}`}>
          <input type="checkbox" checked={checked} onChange={onChange} disabled={!enabled || (busy && !allowWhileRunning)} />
          <span className="toggle-thumb" />
        </span>
      </label>
    </div>
  );
}

function ReportFileCard({ title, kind, icon, path, displayPath = "", available, onOpen, language }) {
  const visiblePath = displayPath || path;
  return (
    <div className={`rsb-file-card${available ? " rsb-file-card--ready" : ""}`}>
      <div className="rsb-file-card__icon">{icon}</div>
      <div className="rsb-file-card__info">
        <strong>{title}</strong>
        <span className="rsb-file-card__kind">{kind}</span>
        {visiblePath ? (
          <span className="rsb-file-card__path" title={visiblePath}>{visiblePath}</span>
        ) : (
          <span className="rsb-file-card__path rsb-file-card__path--empty">
            {language === "ko" ? "Not generated yet" : "Not generated yet"}
          </span>
        )}
      </div>
      <div className="rsb-file-card__actions">
        <span className={`status-badge status-badge--${available ? "success" : "neutral"}`}>
          {available ? (language === "ko" ? "Ready" : "Ready") : (language === "ko" ? "Pending" : "Pending")}
        </span>
        {available && path ? (
          <button className="rsb-file-card__open-btn" onClick={() => onOpen(path)} type="button" title={language === "ko" ? "Open file" : "Open file"}>
            <OpenFolderIcon />
            <span>{language === "ko" ? "Open" : "Open"}</span>
          </button>
        ) : null}
      </div>
    </div>
  );
}

function openInSystemSafe(path) {
  if (path) {
    openInSystem(path).catch(() => {});
  }
}

export const OutputPanel = memo(function OutputPanel({ processOutput = "", language = "en" }) {
  const outputRef = useRef(null);

  useEffect(() => {
    if (outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [processOutput]);

  return (
    <div className="details-output-panel rsb-output">
      {processOutput ? (
        <pre ref={outputRef} className="details-output-pre">{processOutput}</pre>
      ) : (
        <div className="details-output-empty">
          <RailTerminalIcon />
          <span>{language === "ko" ? "No output yet." : "No output yet."}</span>
        </div>
      )}
    </div>
  );
});

export const FilesPanel = memo(function FilesPanel({
  detail,
  form,
  busy,
  onChangeForm,
  liveRuntimeEditable,
  language = "en",
}) {
  const { closeoutPath, wordPath, wordTargetPath, pptPath, pptTargetPath, webpagePath, latestFailureArtifactFiles } = useMemo(() => ({
    closeoutPath: String(detail?.files?.closeout_report_file || "").trim(),
    wordPath: String(detail?.reports?.word_report_path || "").trim(),
    wordTargetPath: String(detail?.files?.word_report_file || "").trim(),
    pptPath: String(detail?.reports?.powerpoint_report_path || "").trim(),
    pptTargetPath: String(
      detail?.reports?.powerpoint_report_target_path
      || detail?.files?.powerpoint_report_file
      || "",
    ).trim(),
    webpagePath: String(detail?.reports?.webpage_path || detail?.files?.webpage_file || "").trim(),
    latestFailureArtifactFiles: Array.isArray(detail?.reports?.latest_failure?.artifact_files)
      ? detail.reports.latest_failure.artifact_files
      : [],
  }), [detail?.files, detail?.reports]);

  return (
    <div className="rsb-files">
      <div className="rsb-files__section-label">
        {language === "ko" ? "Document Generation" : "Document Generation"}
      </div>

      <div className="rsb-files__generation">
        <OutputCard
          icon={<WordDocIcon />}
          title="Word Report"
          description={language === "ko" ? "Save execution results as a Word (.docx) report." : "Save execution results as a Word (.docx) report."}
          enabled={Boolean(onChangeForm)}
          checked={Boolean(form?.runtime?.generate_word_report)}
          onChange={(event) =>
            onChangeForm?.((current) => ({
              ...current,
              runtime: { ...current.runtime, generate_word_report: event.target.checked },
            }))
          }
          busy={busy}
          allowWhileRunning={liveRuntimeEditable}
          language={language}
        />
        <OutputCard
          icon={<PptDocIcon />}
          title="PowerPoint"
          description={language === "ko" ? "Auto-generate result slides as a PowerPoint presentation." : "Auto-generate result slides as a PowerPoint presentation."}
          enabled={false}
          checked={false}
          onChange={() => {}}
          busy={busy}
          comingSoon={true}
          language={language}
        />
        <OutputCard
          icon={<WebDocIcon />}
          title={language === "ko" ? "Website" : "Website"}
          description={language === "ko" ? "Export results as a static HTML website." : "Export results as a static HTML website."}
          enabled={false}
          checked={false}
          onChange={() => {}}
          busy={busy}
          comingSoon={true}
          language={language}
        />
      </div>

      <div className="rsb-files__section-label">
        {language === "ko" ? "Reports & Outputs" : "Reports & Outputs"}
      </div>

      <ReportFileCard title={language === "ko" ? "Closeout Report" : "Closeout Report"} kind="Markdown" icon={<MarkdownDocIcon />} path={closeoutPath} available={Boolean(detail?.reports?.closeout_report_text && closeoutPath)} onOpen={openInSystemSafe} language={language} />
      <ReportFileCard title="Word Report" kind=".docx" icon={<WordDocIcon />} path={wordPath} displayPath={wordPath || wordTargetPath} available={Boolean(wordPath)} onOpen={openInSystemSafe} language={language} />
      <ReportFileCard title="PowerPoint" kind=".pptx" icon={<PptDocIcon />} path={pptPath} displayPath={pptPath || pptTargetPath} available={Boolean(pptPath)} onOpen={openInSystemSafe} language={language} />
      {webpagePath ? <ReportFileCard title="Webpage" kind=".html" icon={<WebDocIcon />} path={webpagePath} available={true} onOpen={openInSystemSafe} language={language} /> : null}

      {latestFailureArtifactFiles.length ? (
        <>
          <div className="rsb-files__section-label" style={{ marginTop: "12px" }}>
            {language === "ko" ? "Failure Artifacts" : "Failure Artifacts"}
          </div>
          {latestFailureArtifactFiles.slice(0, 6).map((path) => (
            <div key={path} className="rsb-artifact-row">
              <span className="rsb-artifact-row__path" title={path}>{path}</span>
              <button className="rsb-file-card__open-btn" onClick={() => openInSystemSafe(path)} type="button" title={language === "ko" ? "Open" : "Open"}>
                <OpenFolderIcon />
              </button>
            </div>
          ))}
        </>
      ) : null}
    </div>
  );
});

function seededCommonRequirementDraft(item, spineCurrentVersion) {
  return {
    title: String(item?.title || ""),
    reason: String(item?.reason || ""),
    notes: String(item?.notes || ""),
    affectedPaths: Array.isArray(item?.affected_paths) ? item.affected_paths.join(", ") : "",
    sharedContracts: Array.isArray(item?.shared_contracts) ? item.shared_contracts.join(", ") : "",
    promotionClass: String(item?.promotion_class || "yellow"),
    stepId: String(item?.step_id || ""),
    lineageId: String(item?.lineage_id || ""),
    spineVersion: String(item?.spine_version || spineCurrentVersion || "spine-v1"),
  };
}

function seededSpineCheckpointDraft(item) {
  return {
    version: String(item?.version || ""),
    notes: String(item?.notes || ""),
    sharedContracts: Array.isArray(item?.shared_contracts) ? item.shared_contracts.join(", ") : "",
    touchedFiles: Array.isArray(item?.touched_files) ? item.touched_files.join(", ") : "",
    stepId: String(item?.step_id || ""),
    lineageId: String(item?.lineage_id || ""),
    commitHash: String(item?.commit_hash || ""),
  };
}

export const ContractsPanel = memo(function ContractsPanel({
  detail,
  selectedStep,
  busy,
  onResolveCommonRequirement,
  onReopenCommonRequirement,
  onRecordSpineCheckpoint,
  onUpdateCommonRequirement,
  onDeleteCommonRequirement,
  onUpdateSpineCheckpoint,
  onDeleteSpineCheckpoint,
  language = "en",
}) {
  const [commonRequirementDrafts, setCommonRequirementDrafts] = useState({});
  const [spineCheckpointDrafts, setSpineCheckpointDrafts] = useState({});
  const [checkpointVersionDraft, setCheckpointVersionDraft] = useState("");
  const [checkpointNoteDraft, setCheckpointNoteDraft] = useState("");
  const [checkpointContractsDraft, setCheckpointContractsDraft] = useState("");

  const selectedStepContracts = Array.isArray(selectedStep?.shared_contracts) ? selectedStep.shared_contracts : [];
  const selectedPrimaryScope = Array.isArray(selectedStep?.primary_scope_paths) ? selectedStep.primary_scope_paths : [];
  const selectedSharedReviewed = Array.isArray(selectedStep?.shared_reviewed_paths) ? selectedStep.shared_reviewed_paths : [];
  const selectedForbiddenCore = Array.isArray(selectedStep?.forbidden_core_paths) ? selectedStep.forbidden_core_paths : [];
  const spineCurrentVersion = String(detail?.reports?.spine?.current_version || "spine-v1");
  const spineReport = detail?.reports?.spine || {};
  const commonRequirements = detail?.reports?.common_requirements || {};
  const lineageManifestSummary = detail?.reports?.lineage_manifest_summary || {};
  const contractWaveAudit = detail?.reports?.contract_wave_audit || {};
  const lineageManifests = Array.isArray(detail?.reports?.lineage_manifests) ? detail.reports.lineage_manifests : [];
  const openCommonRequirements = Array.isArray(commonRequirements?.open_items) ? commonRequirements.open_items : [];
  const resolvedCommonRequirements = Array.isArray(commonRequirements?.resolved_items) ? commonRequirements.resolved_items : [];
  const spineHistory = Array.isArray(spineReport?.recent_history) ? spineReport.recent_history : [];
  const sharedContractsText = String(detail?.reports?.shared_contracts_text || "").trim();
  const spinePath = String(detail?.files?.spine_file || detail?.reports?.spine?.path || "").trim();
  const commonRequirementsPath = String(detail?.files?.common_requirements_file || detail?.reports?.common_requirements?.path || "").trim();
  const contractWaveAuditItems = Array.isArray(contractWaveAudit?.recent_items) ? contractWaveAudit.recent_items : [];
  const contractWaveAuditPath = String(detail?.files?.contract_wave_audit_file || contractWaveAudit?.path || "").trim();
  const sharedContractsPath = String(detail?.files?.shared_contracts_file || detail?.reports?.shared_contracts_path || "").trim();
  const lineageManifestsDir = String(detail?.files?.lineage_manifests_dir || detail?.reports?.lineage_manifests_dir || "").trim();
  const contractAttention =
    Number(commonRequirements?.open_count || 0) > 0
    || Number(lineageManifestSummary?.yellow_count || 0) > 0
    || Number(lineageManifestSummary?.red_count || 0) > 0;

  useEffect(() => {
    setCheckpointVersionDraft(spineCurrentVersion);
  }, [detail?.project?.repo_id, spineCurrentVersion]);

  useEffect(() => {
    setCommonRequirementDrafts({});
    setSpineCheckpointDrafts({});
    setCheckpointNoteDraft("");
    setCheckpointContractsDraft(selectedStepContracts.join(", "));
  }, [detail?.project?.repo_id, selectedStep?.step_id, selectedStepContracts]);

  function commonRequirementDraft(item) {
    const requestId = String(item?.request_id || "");
    return commonRequirementDrafts?.[requestId] || seededCommonRequirementDraft(item, spineCurrentVersion);
  }

  function updateCommonRequirementDraft(item, patch) {
    const requestId = String(item?.request_id || "");
    if (!requestId) {
      return;
    }
    setCommonRequirementDrafts((current) => ({
      ...current,
      [requestId]: {
        ...seededCommonRequirementDraft(item, spineCurrentVersion),
        ...(current?.[requestId] || {}),
        ...patch,
      },
    }));
  }

  function spineCheckpointDraft(item) {
    const checkpointId = String(item?.checkpoint_id || "");
    return spineCheckpointDrafts?.[checkpointId] || seededSpineCheckpointDraft(item);
  }

  function updateSpineCheckpointDraft(item, patch) {
    const checkpointId = String(item?.checkpoint_id || "");
    if (!checkpointId) {
      return;
    }
    setSpineCheckpointDrafts((current) => ({
      ...current,
      [checkpointId]: {
        ...seededSpineCheckpointDraft(item),
        ...(current?.[checkpointId] || {}),
        ...patch,
      },
    }));
  }

  async function handleResolveCommonRequirement(requestId) {
    const item = [...openCommonRequirements, ...resolvedCommonRequirements].find((entry) => entry?.request_id === requestId) || {};
    const draft = commonRequirementDraft(item);
    const succeeded = await Promise.resolve(onResolveCommonRequirement?.(requestId, draft.notes));
    if (succeeded) {
      setCommonRequirementDrafts((current) => {
        const next = { ...current };
        delete next[requestId];
        return next;
      });
    }
  }

  async function handleReopenCommonRequirement(requestId) {
    const item = [...openCommonRequirements, ...resolvedCommonRequirements].find((entry) => entry?.request_id === requestId) || {};
    const draft = commonRequirementDraft(item);
    const succeeded = await Promise.resolve(onReopenCommonRequirement?.(requestId, draft.notes));
    if (succeeded) {
      setCommonRequirementDrafts((current) => {
        const next = { ...current };
        delete next[requestId];
        return next;
      });
    }
  }

  async function handleRecordSpineCheckpoint() {
    const succeeded = await Promise.resolve(onRecordSpineCheckpoint?.({
      version: checkpointVersionDraft,
      notes: checkpointNoteDraft,
      sharedContracts: checkpointContractsDraft,
    }));
    if (succeeded) {
      setCheckpointNoteDraft("");
    }
  }

  async function handleSaveCommonRequirement(item) {
    const draft = commonRequirementDraft(item);
    const succeeded = await Promise.resolve(onUpdateCommonRequirement?.(item.request_id, draft));
    if (succeeded) {
      setCommonRequirementDrafts((current) => {
        const next = { ...current };
        delete next[item.request_id];
        return next;
      });
    }
  }

  async function handleDeleteCommonRequirement(item) {
    const draft = commonRequirementDraft(item);
    const succeeded = await Promise.resolve(onDeleteCommonRequirement?.(item.request_id, draft.notes));
    if (succeeded) {
      setCommonRequirementDrafts((current) => {
        const next = { ...current };
        delete next[item.request_id];
        return next;
      });
    }
  }

  async function handleSaveSpineCheckpoint(item) {
    const draft = spineCheckpointDraft(item);
    const succeeded = await Promise.resolve(onUpdateSpineCheckpoint?.(item.checkpoint_id, draft));
    if (succeeded) {
      setSpineCheckpointDrafts((current) => {
        const next = { ...current };
        delete next[item.checkpoint_id];
        return next;
      });
    }
  }

  async function handleDeleteSpineCheckpoint(item) {
    const draft = spineCheckpointDraft(item);
    const succeeded = await Promise.resolve(onDeleteSpineCheckpoint?.(item.checkpoint_id, draft.notes));
    if (succeeded) {
      setSpineCheckpointDrafts((current) => {
        const next = { ...current };
        delete next[item.checkpoint_id];
        return next;
      });
    }
  }

  return (
    <div className="rsb-inspector">
      <section className="details-card">
        <div className="details-card__header">
          <strong>{language === "ko" ? "Contract Wave" : "Contract Wave"}</strong>
          <span className={`status-badge status-badge--${contractAttention ? "warning" : "success"}`}>
            {contractAttention ? (language === "ko" ? "Needs review" : "Needs review") : (language === "ko" ? "Stable" : "Stable")}
          </span>
        </div>
        <dl className="details-list">
          <div><dt>{language === "ko" ? "Spine" : "Spine"}</dt><dd>{spineCurrentVersion}</dd></div>
          <div><dt>{language === "ko" ? "Open CRRs" : "Open CRRs"}</dt><dd>{Number(commonRequirements?.open_count || 0)}</dd></div>
          <div><dt>{language === "ko" ? "Resolved CRRs" : "Resolved CRRs"}</dt><dd>{Number(commonRequirements?.resolved_count || 0)}</dd></div>
          <div><dt>{language === "ko" ? "Manifests" : "Manifests"}</dt><dd>{Number(lineageManifestSummary?.total || 0)}</dd></div>
          <div>
            <dt>{language === "ko" ? "Promotion mix" : "Promotion mix"}</dt>
            <dd>G {Number(lineageManifestSummary?.green_count || 0)} / Y {Number(lineageManifestSummary?.yellow_count || 0)} / R {Number(lineageManifestSummary?.red_count || 0)}</dd>
          </div>
        </dl>
      </section>

      <section className="details-card">
        <div className="details-card__header">
          <strong>{language === "ko" ? "Artifacts" : "Artifacts"}</strong>
        </div>
        <div style={{ display: "grid", gap: "10px" }}>
          <ReportFileCard title="SPINE.json" kind=".json" icon={<MarkdownDocIcon />} path={spinePath} available={Boolean(spinePath)} onOpen={openInSystemSafe} language={language} />
          <ReportFileCard title="COMMON_REQUIREMENTS.json" kind=".json" icon={<MarkdownDocIcon />} path={commonRequirementsPath} available={Boolean(commonRequirementsPath)} onOpen={openInSystemSafe} language={language} />
          <ReportFileCard title="CONTRACT_WAVE_AUDIT.jsonl" kind=".jsonl" icon={<MarkdownDocIcon />} path={contractWaveAuditPath} available={Boolean(contractWaveAuditPath)} onOpen={openInSystemSafe} language={language} />
          <ReportFileCard title="SHARED_CONTRACTS.md" kind="Markdown" icon={<MarkdownDocIcon />} path={sharedContractsPath} available={Boolean(sharedContractsPath)} onOpen={openInSystemSafe} language={language} />
          <ReportFileCard title={language === "ko" ? "Lineage manifests" : "Lineage manifests"} kind={language === "ko" ? "Directory" : "Directory"} icon={<OpenFolderIcon />} path={lineageManifestsDir} available={Boolean(lineageManifestsDir)} onOpen={openInSystemSafe} language={language} />
        </div>
      </section>

      <section className="details-card">
        <div className="details-card__header">
          <strong>{language === "ko" ? "Spine Controls" : "Spine Controls"}</strong>
        </div>
        <div style={{ display: "grid", gap: "10px" }}>
          <label className="details-text" style={{ display: "grid", gap: "4px" }}>
            <strong>{language === "ko" ? "Version" : "Version"}</strong>
            <input value={checkpointVersionDraft} onChange={(event) => setCheckpointVersionDraft(event.target.value)} disabled={busy || !onRecordSpineCheckpoint} placeholder="spine-v1" style={{ width: "100%" }} />
          </label>
          <label className="details-text" style={{ display: "grid", gap: "4px" }}>
            <strong>{language === "ko" ? "Shared contracts" : "Shared contracts"}</strong>
            <input value={checkpointContractsDraft} onChange={(event) => setCheckpointContractsDraft(event.target.value)} disabled={busy || !onRecordSpineCheckpoint} placeholder={language === "ko" ? "api/payments, schema/profile" : "api/payments, schema/profile"} style={{ width: "100%" }} />
          </label>
          <label className="details-text" style={{ display: "grid", gap: "4px" }}>
            <strong>{language === "ko" ? "Notes" : "Notes"}</strong>
            <textarea value={checkpointNoteDraft} onChange={(event) => setCheckpointNoteDraft(event.target.value)} disabled={busy || !onRecordSpineCheckpoint} placeholder={language === "ko" ? "Why this checkpoint matters" : "Why this checkpoint matters"} rows={3} style={{ width: "100%", resize: "vertical" }} />
          </label>
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <button className="toolbar-button toolbar-button--ghost" onClick={() => { void handleRecordSpineCheckpoint(); }} type="button" disabled={busy || !onRecordSpineCheckpoint}>
              {language === "ko" ? "Record checkpoint" : "Record checkpoint"}
            </button>
          </div>
        </div>
      </section>

      {selectedStep ? (
        <section className="details-card">
          <div className="details-card__header">
            <strong>{language === "ko" ? "Selected Step Policy" : "Selected Step Policy"}</strong>
            <span className={`status-badge status-badge--${statusTone(selectedStep.promotion_class || "pending")}`}>
              {String(selectedStep.promotion_class || "-").toUpperCase()}
            </span>
          </div>
          <div className="details-text">
            <strong>{selectedStep.step_id}: {selectedStep.title}</strong>
            <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>{language === "ko" ? "Step type" : "Step type"}: {selectedStep.step_type || "feature"} | {language === "ko" ? "Scope" : "Scope"}: {selectedStep.scope_class || "free_owned"} | {language === "ko" ? "Spine" : "Spine"}: {selectedStep.spine_version || spineCurrentVersion || "spine-v1"}</p>
            <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>Contracts: {selectedStepContracts.length ? selectedStepContracts.join(", ") : "none"}</p>
            <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>Primary: {selectedPrimaryScope.length ? selectedPrimaryScope.join(", ") : "none"}</p>
            <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>Shared-reviewed: {selectedSharedReviewed.length ? selectedSharedReviewed.join(", ") : "none"}</p>
            <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>Forbidden-core: {selectedForbiddenCore.length ? selectedForbiddenCore.join(", ") : "none"}</p>
          </div>
        </section>
      ) : null}

      <section className="details-card">
        <div className="details-card__header">
          <strong>{language === "ko" ? "Open Common Requirements" : "Open Common Requirements"}</strong>
        </div>
        {openCommonRequirements.length ? (
          <div style={{ display: "grid", gap: "10px" }}>
            {openCommonRequirements.slice(0, 6).map((item) => {
              const draft = commonRequirementDraft(item);
              return (
                <div key={item.request_id} className="details-text">
                  <strong>{item.request_id} / {draft.title || (language === "ko" ? "Shared requirement review" : "Shared requirement review")}</strong>
                  <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>
                    {String(draft.promotionClass || "").toUpperCase()} | {draft.spineVersion || spineCurrentVersion || "spine-v1"} | {draft.lineageId || "n/a"} / {draft.stepId || "n/a"}
                  </p>
                  <div style={{ display: "grid", gap: "6px", marginTop: "6px" }}>
                    <input value={draft.title} onChange={(event) => updateCommonRequirementDraft(item, { title: event.target.value })} disabled={busy || !onUpdateCommonRequirement} placeholder={language === "ko" ? "Title" : "Title"} style={{ width: "100%" }} />
                    <textarea value={draft.reason} onChange={(event) => updateCommonRequirementDraft(item, { reason: event.target.value })} disabled={busy || !onUpdateCommonRequirement} placeholder={language === "ko" ? "Reason" : "Reason"} rows={2} style={{ width: "100%", resize: "vertical" }} />
                    <input value={draft.sharedContracts} onChange={(event) => updateCommonRequirementDraft(item, { sharedContracts: event.target.value })} disabled={busy || !onUpdateCommonRequirement} placeholder={language === "ko" ? "Shared contracts" : "Shared contracts"} style={{ width: "100%" }} />
                    <input value={draft.affectedPaths} onChange={(event) => updateCommonRequirementDraft(item, { affectedPaths: event.target.value })} disabled={busy || !onUpdateCommonRequirement} placeholder={language === "ko" ? "Affected paths" : "Affected paths"} style={{ width: "100%" }} />
                    <textarea value={draft.notes} onChange={(event) => updateCommonRequirementDraft(item, { notes: event.target.value })} disabled={busy || (!onResolveCommonRequirement && !onUpdateCommonRequirement)} placeholder={language === "ko" ? "Operator note" : "Operator note"} rows={2} style={{ width: "100%", resize: "vertical" }} />
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px" }}>
                      <input value={draft.stepId} onChange={(event) => updateCommonRequirementDraft(item, { stepId: event.target.value })} disabled={busy || !onUpdateCommonRequirement} placeholder="step_id" style={{ width: "100%" }} />
                      <input value={draft.lineageId} onChange={(event) => updateCommonRequirementDraft(item, { lineageId: event.target.value })} disabled={busy || !onUpdateCommonRequirement} placeholder="lineage_id" style={{ width: "100%" }} />
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px" }}>
                      <input value={draft.spineVersion} onChange={(event) => updateCommonRequirementDraft(item, { spineVersion: event.target.value })} disabled={busy || !onUpdateCommonRequirement} placeholder="spine_version" style={{ width: "100%" }} />
                      <select value={draft.promotionClass || "yellow"} onChange={(event) => updateCommonRequirementDraft(item, { promotionClass: event.target.value })} disabled={busy || !onUpdateCommonRequirement}>
                        <option value="green">green</option>
                        <option value="yellow">yellow</option>
                        <option value="red">red</option>
                      </select>
                    </div>
                    <div style={{ display: "flex", justifyContent: "flex-end", gap: "6px", flexWrap: "wrap" }}>
                      <button className="toolbar-button toolbar-button--ghost" onClick={() => { void handleSaveCommonRequirement(item); }} type="button" disabled={busy || !onUpdateCommonRequirement}>{language === "ko" ? "Save" : "Save"}</button>
                      <button className="toolbar-button toolbar-button--ghost" onClick={() => { void handleResolveCommonRequirement(item.request_id); }} type="button" disabled={busy || !onResolveCommonRequirement}>{language === "ko" ? "Resolve" : "Resolve"}</button>
                      <button className="toolbar-button toolbar-button--ghost" onClick={() => { void handleDeleteCommonRequirement(item); }} type="button" disabled={busy || !onDeleteCommonRequirement}>{language === "ko" ? "Delete" : "Delete"}</button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="details-text" style={{ color: "var(--text-dim)", fontSize: "11px" }}>
            {language === "ko" ? "No open CRRs." : "No open CRRs."}
          </div>
        )}
      </section>

      <section className="details-card">
        <div className="details-card__header">
          <strong>{language === "ko" ? "Recent Manifests" : "Recent Manifests"}</strong>
        </div>
        {lineageManifests.length ? (
          <div style={{ display: "grid", gap: "10px" }}>
            {lineageManifests.slice(0, 6).map((item) => (
              <div key={item.manifest_id || `${item.lineage_id}-${item.step_id}`} className="details-text">
                <strong>{item.lineage_id || "LN?"} / {item.step_id || "ST?"}</strong>
                <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>
                  {String(item.promotion_class || "-").toUpperCase()} | {item.step_type || "feature"} | {item.scope_class || "free_owned"}
                </p>
                <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>{item.promotion_reason || "-"}</p>
                <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>
                  Helpers: {Array.isArray(item.helper_symbol_changes) && item.helper_symbol_changes.length ? item.helper_symbol_changes.length : 0} | APIs: {Array.isArray(item.public_symbol_changes) && item.public_symbol_changes.length ? item.public_symbol_changes.length : 0}
                </p>
              </div>
            ))}
          </div>
        ) : (
          <div className="details-text" style={{ color: "var(--text-dim)", fontSize: "11px" }}>
            {language === "ko" ? "No lineage manifests recorded yet." : "No lineage manifests recorded yet."}
          </div>
        )}
      </section>

      {spineHistory.length ? (
        <section className="details-card">
          <div className="details-card__header">
            <strong>{language === "ko" ? "Recent Spine Checkpoints" : "Recent Spine Checkpoints"}</strong>
          </div>
          <div style={{ display: "grid", gap: "10px" }}>
            {spineHistory.slice(0, 5).map((item) => {
              const draft = spineCheckpointDraft(item);
              return (
                <div key={item.checkpoint_id || `${item.version}-${item.created_at}`} className="details-text">
                  <strong>{draft.version || item.version}</strong>
                  <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>
                    {item.created_at || "-"} | {draft.lineageId || "n/a"} / {draft.stepId || "n/a"}
                  </p>
                  <div style={{ display: "grid", gap: "6px", marginTop: "6px" }}>
                    <input value={draft.version} onChange={(event) => updateSpineCheckpointDraft(item, { version: event.target.value })} disabled={busy || !onUpdateSpineCheckpoint} placeholder="version" style={{ width: "100%" }} />
                    <input value={draft.sharedContracts} onChange={(event) => updateSpineCheckpointDraft(item, { sharedContracts: event.target.value })} disabled={busy || !onUpdateSpineCheckpoint} placeholder={language === "ko" ? "Shared contracts" : "Shared contracts"} style={{ width: "100%" }} />
                    <input value={draft.touchedFiles} onChange={(event) => updateSpineCheckpointDraft(item, { touchedFiles: event.target.value })} disabled={busy || !onUpdateSpineCheckpoint} placeholder={language === "ko" ? "Touched files" : "Touched files"} style={{ width: "100%" }} />
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px" }}>
                      <input value={draft.stepId} onChange={(event) => updateSpineCheckpointDraft(item, { stepId: event.target.value })} disabled={busy || !onUpdateSpineCheckpoint} placeholder="step_id" style={{ width: "100%" }} />
                      <input value={draft.lineageId} onChange={(event) => updateSpineCheckpointDraft(item, { lineageId: event.target.value })} disabled={busy || !onUpdateSpineCheckpoint} placeholder="lineage_id" style={{ width: "100%" }} />
                    </div>
                    <input value={draft.commitHash} onChange={(event) => updateSpineCheckpointDraft(item, { commitHash: event.target.value })} disabled={busy || !onUpdateSpineCheckpoint} placeholder="commit_hash" style={{ width: "100%" }} />
                    <textarea value={draft.notes} onChange={(event) => updateSpineCheckpointDraft(item, { notes: event.target.value })} disabled={busy || (!onUpdateSpineCheckpoint && !onDeleteSpineCheckpoint)} placeholder={language === "ko" ? "Checkpoint note" : "Checkpoint note"} rows={2} style={{ width: "100%", resize: "vertical" }} />
                    <div style={{ display: "flex", justifyContent: "flex-end", gap: "6px", flexWrap: "wrap" }}>
                      <button className="toolbar-button toolbar-button--ghost" onClick={() => { void handleSaveSpineCheckpoint(item); }} type="button" disabled={busy || !onUpdateSpineCheckpoint}>{language === "ko" ? "Save" : "Save"}</button>
                      <button className="toolbar-button toolbar-button--ghost" onClick={() => { void handleDeleteSpineCheckpoint(item); }} type="button" disabled={busy || !onDeleteSpineCheckpoint}>{language === "ko" ? "Delete" : "Delete"}</button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      ) : null}

      {sharedContractsText ? (
        <section className="details-card">
          <div className="details-card__header">
            <strong>{language === "ko" ? "Shared Contracts Snapshot" : "Shared Contracts Snapshot"}</strong>
          </div>
          <div className="details-text">
            <pre style={{ whiteSpace: "pre-wrap", fontSize: "11px" }}>{sharedContractsText}</pre>
          </div>
        </section>
      ) : null}

      {contractWaveAuditItems.length ? (
        <section className="details-card">
          <div className="details-card__header">
            <strong>{language === "ko" ? "Contract Wave Audit" : "Contract Wave Audit"}</strong>
          </div>
          <div style={{ display: "grid", gap: "10px" }}>
            {contractWaveAuditItems.slice(0, 6).map((item, index) => (
              <div key={`${item.timestamp || "audit"}-${index}`} className="details-text">
                <strong>{String(item.action || "update").toUpperCase()} / {item.entity_type || "contract_wave"}</strong>
                <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>{item.timestamp || "-"} | {item.entity_id || "n/a"}</p>
                <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>{item.note || "-"}</p>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {resolvedCommonRequirements.length ? (
        <section className="details-card">
          <div className="details-card__header">
            <strong>{language === "ko" ? "Resolved Common Requirements" : "Resolved Common Requirements"}</strong>
          </div>
          <div style={{ display: "grid", gap: "10px" }}>
            {resolvedCommonRequirements.slice(0, 4).map((item) => {
              const draft = commonRequirementDraft(item);
              return (
                <div key={item.request_id} className="details-text">
                  <strong>{item.request_id} / {draft.title || "-"}</strong>
                  <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>{item.resolved_at || "-"} | {draft.lineageId || "n/a"} / {draft.stepId || "n/a"}</p>
                  <div style={{ display: "grid", gap: "6px", marginTop: "6px" }}>
                    <input value={draft.title} onChange={(event) => updateCommonRequirementDraft(item, { title: event.target.value })} disabled={busy || !onUpdateCommonRequirement} placeholder={language === "ko" ? "Title" : "Title"} style={{ width: "100%" }} />
                    <textarea value={draft.reason} onChange={(event) => updateCommonRequirementDraft(item, { reason: event.target.value })} disabled={busy || !onUpdateCommonRequirement} placeholder={language === "ko" ? "Reason" : "Reason"} rows={2} style={{ width: "100%", resize: "vertical" }} />
                    <input value={draft.sharedContracts} onChange={(event) => updateCommonRequirementDraft(item, { sharedContracts: event.target.value })} disabled={busy || !onUpdateCommonRequirement} placeholder={language === "ko" ? "Shared contracts" : "Shared contracts"} style={{ width: "100%" }} />
                    <input value={draft.affectedPaths} onChange={(event) => updateCommonRequirementDraft(item, { affectedPaths: event.target.value })} disabled={busy || !onUpdateCommonRequirement} placeholder={language === "ko" ? "Affected paths" : "Affected paths"} style={{ width: "100%" }} />
                    <textarea value={draft.notes} onChange={(event) => updateCommonRequirementDraft(item, { notes: event.target.value })} disabled={busy || (!onReopenCommonRequirement && !onUpdateCommonRequirement)} placeholder={language === "ko" ? "Operator note" : "Operator note"} rows={2} style={{ width: "100%", resize: "vertical" }} />
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px" }}>
                      <input value={draft.stepId} onChange={(event) => updateCommonRequirementDraft(item, { stepId: event.target.value })} disabled={busy || !onUpdateCommonRequirement} placeholder="step_id" style={{ width: "100%" }} />
                      <input value={draft.lineageId} onChange={(event) => updateCommonRequirementDraft(item, { lineageId: event.target.value })} disabled={busy || !onUpdateCommonRequirement} placeholder="lineage_id" style={{ width: "100%" }} />
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px" }}>
                      <input value={draft.spineVersion} onChange={(event) => updateCommonRequirementDraft(item, { spineVersion: event.target.value })} disabled={busy || !onUpdateCommonRequirement} placeholder="spine_version" style={{ width: "100%" }} />
                      <select value={draft.promotionClass || "yellow"} onChange={(event) => updateCommonRequirementDraft(item, { promotionClass: event.target.value })} disabled={busy || !onUpdateCommonRequirement}>
                        <option value="green">green</option>
                        <option value="yellow">yellow</option>
                        <option value="red">red</option>
                      </select>
                    </div>
                    <div style={{ display: "flex", justifyContent: "flex-end", gap: "6px", flexWrap: "wrap" }}>
                      <button className="toolbar-button toolbar-button--ghost" onClick={() => { void handleSaveCommonRequirement(item); }} type="button" disabled={busy || !onUpdateCommonRequirement}>{language === "ko" ? "Save" : "Save"}</button>
                      <button className="toolbar-button toolbar-button--ghost" onClick={() => { void handleReopenCommonRequirement(item.request_id); }} type="button" disabled={busy || !onReopenCommonRequirement}>{language === "ko" ? "Reopen" : "Reopen"}</button>
                      <button className="toolbar-button toolbar-button--ghost" onClick={() => { void handleDeleteCommonRequirement(item); }} type="button" disabled={busy || !onDeleteCommonRequirement}>{language === "ko" ? "Delete" : "Delete"}</button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      ) : null}
    </div>
  );
});

export const InspectorPanel = memo(function InspectorPanel({
  detail,
  selectedStep,
  modelPresets,
  activeJob = null,
  language = "en",
}) {
  const { t } = useI18n();
  const pendingCheckpoint = detail?.checkpoints?.pending || null;
  const executionJob = visibleExecutionJob(activeJob);
  const projectStatus = projectStatusWithJob(detail?.project?.current_status || "", executionJob);
  const selectedStepStatus = effectiveStepStatus(selectedStep, projectStatus);

  return (
    <div className="rsb-inspector">
      <section className="details-card">
        <div className="details-card__header">
          <strong>{t("common.project")}</strong>
          <span className={`status-badge status-badge--${statusTone(projectStatus)}`}>
            {displayStatus(projectStatus || "idle", language)}
          </span>
        </div>
        <dl className="details-list">
          <div><dt>{t("common.name")}</dt><dd>{detail?.project?.display_name || detail?.project?.slug || t("project.none")}</dd></div>
          <div><dt>{t("common.branch")}</dt><dd>{detail?.project?.branch || t("common.unknown")}</dd></div>
          <div><dt>Path</dt><dd>{detail?.project?.repo_path || t("common.unknown")}</dd></div>
          <div><dt>Model</dt><dd>{runtimeSummary(detail?.runtime || {}, modelPresets)}</dd></div>
          <div><dt>Revision</dt><dd>{detail?.project?.current_safe_revision || "-"}</dd></div>
        </dl>
      </section>

      <section className="details-card">
        <div className="details-card__header">
          <strong>Step</strong>
          <span className={`status-badge status-badge--${statusTone(selectedStepStatus)}`}>
            {selectedStep ? displayStatus(selectedStepStatus, language) : "-"}
          </span>
        </div>
        {selectedStep ? (
          <div className="details-text">
            <strong>{selectedStep.step_id}: {selectedStep.title}</strong>
            <p style={{ margin: "4px 0", color: "var(--text-muted)" }}>{selectedStep.display_description}</p>
            <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>Effort: {reasoningEffortLabel(selectedStep.reasoning_effort || detail?.runtime?.effort || "high")}</p>
            {selectedStep.success_criteria ? <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>{selectedStep.success_criteria}</p> : null}
            {selectedStep.deadline_at ? <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>Deadline: {selectedStep.deadline_at}</p> : null}
          </div>
        ) : (
          <div className="details-text" style={{ color: "var(--text-dim)", fontSize: "11px" }}>
            {language === "ko" ? "Select a block to inspect." : "Select a block to inspect."}
          </div>
        )}
      </section>

      {pendingCheckpoint ? (
        <section className="details-card">
          <div className="details-card__header">
            <strong>Checkpoint</strong>
            <span className={`status-badge status-badge--${statusTone(pendingCheckpoint.status)}`}>
              {displayStatus(pendingCheckpoint.status || "pending", language)}
            </span>
          </div>
          <div className="details-text">
            <strong>{formatCheckpointDisplayId(pendingCheckpoint.checkpoint_id)}</strong>
            {pendingCheckpoint.title ? <p style={{ margin: "4px 0" }}>{pendingCheckpoint.title}</p> : null}
            {pendingCheckpoint.target_block ? <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>Block {pendingCheckpoint.target_block}</p> : null}
            {pendingCheckpoint.deadline_at ? <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>Deadline: {pendingCheckpoint.deadline_at}</p> : null}
          </div>
        </section>
      ) : null}

      {detail?.reports?.closeout_report_text ? (
        <section className="details-card">
          <div className="details-card__header">
            <strong>Report</strong>
          </div>
          <div className="details-text">
            <pre style={{ whiteSpace: "pre-wrap", fontSize: "11px" }}>{detail.reports.closeout_report_text}</pre>
          </div>
        </section>
      ) : null}
    </div>
  );
});
