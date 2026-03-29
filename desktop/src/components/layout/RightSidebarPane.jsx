import { useEffect, useRef, useState } from "react";
import { useI18n } from "../../i18n";
import { displayStatus } from "../../locale";
import { effectiveStepStatus, reasoningEffortLabel, runtimeSummary, statusTone } from "../../utils";
import { openInSystem } from "../../api";

/* ── Icons ── */
function SendIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M22 2L11 13M22 2L15 22l-4-9-9-4 20-7z" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ChatIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" width="13" height="13">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function TerminalIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" width="13" height="13">
      <rect x="2" y="4" width="20" height="16" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M6 9l4 3-4 3M13 15h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function FilesIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" width="13" height="13">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <polyline points="14 2 14 8 20 8" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  );
}

function InspectorIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" width="13" height="13">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" />
      <path d="M12 8v4M12 16h.01" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
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

/* ── Report file card ── */
function ReportFileCard({ title, kind, icon, path, available, onOpen, language }) {
  return (
    <div className={`rsb-file-card${available ? " rsb-file-card--ready" : ""}`}>
      <div className="rsb-file-card__icon">{icon}</div>
      <div className="rsb-file-card__info">
        <strong>{title}</strong>
        <span className="rsb-file-card__kind">{kind}</span>
        {path ? (
          <span className="rsb-file-card__path" title={path}>{path}</span>
        ) : (
          <span className="rsb-file-card__path rsb-file-card__path--empty">
            {language === "ko" ? "아직 생성되지 않음" : "Not generated yet"}
          </span>
        )}
      </div>
      <div className="rsb-file-card__actions">
        <span className={`status-badge status-badge--${available ? "success" : "neutral"}`}>
          {available ? (language === "ko" ? "완료" : "Ready") : (language === "ko" ? "대기" : "Pending")}
        </span>
        {available && path ? (
          <button
            className="rsb-file-card__open-btn"
            onClick={() => onOpen(path)}
            type="button"
            title={language === "ko" ? "파일 열기" : "Open file"}
          >
            <OpenFolderIcon />
            <span>{language === "ko" ? "열기" : "Open"}</span>
          </button>
        ) : null}
      </div>
    </div>
  );
}

/* ── Main component ── */
export function RightSidebarPane({ detail, planDraft, selectedStepId, modelPresets, onHide, busy }) {
  const { language, t } = useI18n();
  const [activeTab, setActiveTab] = useState("chat");

  /* Chat state (local – no backend connection yet) */
  const [chatInput, setChatInput] = useState("");
  const [chatMessages, setChatMessages] = useState([]);
  const chatBottomRef = useRef(null);
  const outputRef = useRef(null);

  /* Derived data */
  const processOutput = detail?.subprocess_output || detail?.agent_output || detail?.process_log || "";
  const selectedStep = (planDraft?.steps || []).find((s) => s.step_id === selectedStepId) || null;
  const pendingCheckpoint = detail?.checkpoints?.pending || null;
  const selectedStepStatus = effectiveStepStatus(selectedStep, detail?.project?.current_status || "");

  /* Report file paths */
  const closeoutPath = String(detail?.files?.closeout_report_file || "").trim();
  const wordPath = String(detail?.reports?.word_report_path || detail?.files?.word_report_file || "").trim();
  const pptPath = String(
    detail?.reports?.powerpoint_report_path ||
    detail?.reports?.powerpoint_report_target_path ||
    detail?.files?.powerpoint_report_file || ""
  ).trim();
  const webpagePath = String(detail?.reports?.webpage_path || detail?.files?.webpage_file || "").trim();
  const mlReportPath = String(detail?.files?.ml_experiment_report_file || "").trim();

  /* Scroll chat to bottom on new messages */
  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  /* Scroll output to bottom on new output */
  useEffect(() => {
    if (activeTab === "output" && outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [processOutput, activeTab]);

  function handleSendChat() {
    const text = chatInput.trim();
    if (!text) return;
    setChatMessages((prev) => [...prev, { role: "user", text, id: Date.now() }]);
    setChatInput("");
  }

  function handleChatKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendChat();
    }
  }

  function handleOpenFile(path) {
    if (path) openInSystem(path).catch(() => {});
  }

  const hasOutput = Boolean(processOutput);
  const hasFiles = Boolean(closeoutPath || wordPath || pptPath || webpagePath || mlReportPath);

  return (
    <aside className="details-pane rsb">
      {/* ── Tab bar ── */}
      <div className="rsb-tabbar">
        <div className="tool-tabs">
          <button
            className={`tool-tab rsb-tab${activeTab === "chat" ? " active" : ""}`}
            onClick={() => setActiveTab("chat")}
            type="button"
            title={language === "ko" ? "AI 채팅" : "AI Chat"}
          >
            <ChatIcon />
            <span>{language === "ko" ? "채팅" : "Chat"}</span>
          </button>
          <button
            className={`tool-tab rsb-tab${activeTab === "output" ? " active" : ""}`}
            onClick={() => setActiveTab("output")}
            type="button"
            title={language === "ko" ? "프로세스 출력" : "Process Output"}
          >
            <TerminalIcon />
            <span>Output</span>
            {hasOutput ? <span className="details-output-dot" /> : null}
          </button>
          <button
            className={`tool-tab rsb-tab${activeTab === "files" ? " active" : ""}`}
            onClick={() => setActiveTab("files")}
            type="button"
            title={language === "ko" ? "보고서 및 파일" : "Reports & Files"}
          >
            <FilesIcon />
            <span>{language === "ko" ? "파일" : "Files"}</span>
            {hasFiles ? <span className="rsb-files-dot" /> : null}
          </button>
          <button
            className={`tool-tab rsb-tab${activeTab === "inspector" ? " active" : ""}`}
            onClick={() => setActiveTab("inspector")}
            type="button"
            title="Inspector"
          >
            <InspectorIcon />
            <span>Info</span>
          </button>
        </div>
        {onHide ? (
          <button
            className="tool-window__header-btn"
            onClick={onHide}
            type="button"
            title={`${t("action.dismiss")} (Alt+R)`}
            aria-label="Hide panel"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        ) : null}
      </div>

      {/* ── Chat tab ── */}
      {activeTab === "chat" ? (
        <div className="rsb-chat">
          <div className="rsb-chat__messages">
            {chatMessages.length === 0 ? (
              <div className="rsb-chat__empty">
                <ChatIcon />
                <p>{language === "ko" ? "AI에게 메시지를 보내 실행을 안내하세요." : "Send a message to guide the AI during execution."}</p>
              </div>
            ) : (
              chatMessages.map((msg) => (
                <div key={msg.id} className={`sidebar-chat-bubble sidebar-chat-bubble--${msg.role}`}>
                  <span className="sidebar-chat-bubble__role">
                    {msg.role === "user" ? (language === "ko" ? "나" : "You") : "AI"}
                  </span>
                  <p>{msg.text}</p>
                </div>
              ))
            )}
            <div ref={chatBottomRef} />
          </div>

          <div className="rsb-chat__input-area">
            <textarea
              className="sidebar-chat-input rsb-chat__textarea"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={handleChatKeyDown}
              placeholder={language === "ko" ? "메시지 입력... (Enter로 전송)" : "Type a message… (Enter to send)"}
              disabled={busy}
              rows={3}
            />
            <button
              className="sidebar-chat-send rsb-chat__send-btn"
              onClick={handleSendChat}
              type="button"
              disabled={busy || !chatInput.trim()}
              title={language === "ko" ? "전송" : "Send"}
            >
              <SendIcon />
            </button>
          </div>
        </div>
      ) : null}

      {/* ── Output tab ── */}
      {activeTab === "output" ? (
        <div className="details-output-panel rsb-output">
          {processOutput ? (
            <pre ref={outputRef} className="details-output-pre">{processOutput}</pre>
          ) : (
            <div className="details-output-empty">
              <TerminalIcon />
              <span>{language === "ko" ? "아직 출력이 없습니다." : "No output yet."}</span>
            </div>
          )}
        </div>
      ) : null}

      {/* ── Files tab ── */}
      {activeTab === "files" ? (
        <div className="rsb-files">
          <div className="rsb-files__section-label">
            {language === "ko" ? "보고서 및 출력물" : "Reports & Outputs"}
          </div>

          <ReportFileCard
            title={language === "ko" ? "클로즈아웃 보고서" : "Closeout Report"}
            kind="Markdown"
            icon={<MarkdownDocIcon />}
            path={closeoutPath}
            available={Boolean(detail?.reports?.closeout_report_text && closeoutPath)}
            onOpen={handleOpenFile}
            language={language}
          />
          <ReportFileCard
            title="Word Report"
            kind=".docx"
            icon={<WordDocIcon />}
            path={wordPath}
            available={Boolean(wordPath)}
            onOpen={handleOpenFile}
            language={language}
          />
          <ReportFileCard
            title="PowerPoint"
            kind=".pptx"
            icon={<PptDocIcon />}
            path={pptPath}
            available={Boolean(pptPath)}
            onOpen={handleOpenFile}
            language={language}
          />
          {webpagePath ? (
            <ReportFileCard
              title="Webpage"
              kind=".html"
              icon={<WebDocIcon />}
              path={webpagePath}
              available={true}
              onOpen={handleOpenFile}
              language={language}
            />
          ) : null}
          {mlReportPath ? (
            <ReportFileCard
              title="ML Experiment Report"
              kind="Markdown"
              icon={<MarkdownDocIcon />}
              path={mlReportPath}
              available={true}
              onOpen={handleOpenFile}
              language={language}
            />
          ) : null}

          {detail?.reports?.latest_failure?.artifact_files?.length ? (
            <>
              <div className="rsb-files__section-label" style={{ marginTop: "12px" }}>
                {language === "ko" ? "실패 아티팩트" : "Failure Artifacts"}
              </div>
              {(detail.reports.latest_failure.artifact_files || []).slice(0, 6).map((p) => (
                <div key={p} className="rsb-artifact-row">
                  <span className="rsb-artifact-row__path" title={p}>{p}</span>
                  <button
                    className="rsb-file-card__open-btn"
                    onClick={() => handleOpenFile(p)}
                    type="button"
                    title={language === "ko" ? "열기" : "Open"}
                  >
                    <OpenFolderIcon />
                  </button>
                </div>
              ))}
            </>
          ) : null}
        </div>
      ) : null}

      {/* ── Inspector tab ── */}
      {activeTab === "inspector" ? (
        <div className="rsb-inspector">
          <section className="details-card">
            <div className="details-card__header">
              <strong>{t("common.project")}</strong>
              <span className={`status-badge status-badge--${statusTone(detail?.project?.current_status)}`}>
                {displayStatus(detail?.project?.current_status || "idle", language)}
              </span>
            </div>
            <dl className="details-list">
              <div>
                <dt>{t("common.name")}</dt>
                <dd>{detail?.project?.display_name || detail?.project?.slug || t("project.none")}</dd>
              </div>
              <div>
                <dt>{t("common.branch")}</dt>
                <dd>{detail?.project?.branch || t("common.unknown")}</dd>
              </div>
              <div>
                <dt>Path</dt>
                <dd>{detail?.project?.repo_path || t("common.unknown")}</dd>
              </div>
              <div>
                <dt>Model</dt>
                <dd>{runtimeSummary(detail?.runtime || {}, modelPresets)}</dd>
              </div>
              <div>
                <dt>Revision</dt>
                <dd>{detail?.project?.current_safe_revision || "—"}</dd>
              </div>
            </dl>
          </section>

          <section className="details-card">
            <div className="details-card__header">
              <strong>Step</strong>
              <span className={`status-badge status-badge--${statusTone(selectedStepStatus)}`}>
                {selectedStep ? displayStatus(selectedStepStatus, language) : "—"}
              </span>
            </div>
            {selectedStep ? (
              <div className="details-text">
                <strong>{selectedStep.step_id}: {selectedStep.title}</strong>
                <p style={{ margin: "4px 0", color: "var(--text-muted)" }}>{selectedStep.display_description}</p>
                <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>
                  Effort: {reasoningEffortLabel(selectedStep.reasoning_effort || detail?.runtime?.effort || "high")}
                </p>
                {selectedStep.success_criteria ? (
                  <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>{selectedStep.success_criteria}</p>
                ) : null}
                {selectedStep.deadline_at ? (
                  <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>
                    Deadline: {selectedStep.deadline_at}
                  </p>
                ) : null}
              </div>
            ) : (
              <div className="details-text" style={{ color: "var(--text-dim)", fontSize: "11px" }}>
                {language === "ko" ? "스텝을 선택하면 여기에 표시됩니다." : "Select a step to inspect."}
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
                <strong>{pendingCheckpoint.checkpoint_id}</strong>
                {pendingCheckpoint.title ? <p style={{ margin: "4px 0" }}>{pendingCheckpoint.title}</p> : null}
                <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>
                  Block {pendingCheckpoint.target_block}
                </p>
                {pendingCheckpoint.deadline_at ? (
                  <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>
                    Deadline: {pendingCheckpoint.deadline_at}
                  </p>
                ) : null}
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
      ) : null}
    </aside>
  );
}
