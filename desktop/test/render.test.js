import assert from "node:assert/strict";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import test, { after } from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";

import { build } from "esbuild";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const desktopRoot = path.resolve(__dirname, "..");
const tempDirs = [];

after(async () => {
  await Promise.all(tempDirs.map((dir) => rm(dir, { recursive: true, force: true })));
});

async function importBundledModule(key, contents) {
  const result = await build({
    absWorkingDir: desktopRoot,
    bundle: true,
    format: "esm",
    platform: "node",
    target: "node20",
    write: false,
    jsx: "automatic",
    jsxImportSource: "react",
    external: ["react", "react-dom/server", "react/jsx-runtime"],
    loader: {
      ".js": "jsx",
      ".jsx": "jsx",
    },
    stdin: {
      contents,
      loader: "jsx",
      resolveDir: desktopRoot,
      sourcefile: `${key}.jsx`,
    },
  });
  const tempRoot = path.join(desktopRoot, ".tmp-render");
  await mkdir(tempRoot, { recursive: true });
  const tempDir = await mkdtemp(path.join(tempRoot, `${key}-`));
  tempDirs.push(tempDir);
  const modulePath = path.join(tempDir, `${key}.mjs`);
  await writeFile(modulePath, result.outputFiles[0].text, "utf-8");
  return import(`${pathToFileURL(modulePath).href}?v=${Date.now()}`);
}

function renderHarnessSnippet(importPath, exportName) {
  return `
    import React from "react";
    import { PassThrough } from "node:stream";
    import { renderToPipeableStream } from "react-dom/server";
    import { I18nProvider } from "./src/i18n.jsx";
    import { ${exportName} } from "${importPath}";

    export async function renderComponent(props) {
      return await new Promise((resolve, reject) => {
        const output = new PassThrough();
        let html = "";
        let settled = false;
        let timeoutHandle = null;
        const finish = (callback) => (value) => {
          if (settled) {
            return;
          }
          settled = true;
          clearTimeout(timeoutHandle);
          callback(value);
        };
        output.on("data", (chunk) => {
          html += chunk.toString();
        });
        output.on("end", finish(() => resolve(html)));
        output.on("error", finish(reject));
        const { pipe, abort } = renderToPipeableStream(
          React.createElement(I18nProvider, { initialLanguage: "en" }, React.createElement(${exportName}, props)),
          {
            onAllReady() {
              pipe(output);
            },
            onError(error) {
              finish(reject)(error);
            },
          },
        );
        timeoutHandle = setTimeout(() => {
          abort();
          finish(reject)(new Error("Timed out waiting for server render."));
        }, 5000);
      });
    }
  `;
}

async function renderBundledComponent(key, importPath, exportName, props) {
  const module = await importBundledModule(key, renderHarnessSnippet(importPath, exportName));
  return module.renderComponent(props);
}

function noop() {}

function baseWorkspaceProps(overrides = {}) {
  return {
    activeTab: "run",
    onChangeTab: noop,
    detail: {
      project: {
        current_status: "plan_ready",
      },
      runtime: {
        execution_mode: "serial",
        effort: "medium",
      },
      run_control: {
        stop_after_current_step: false,
        stop_immediately: false,
      },
    },
    form: {
      runtime: {
        execution_mode: "serial",
      },
    },
    shareSettings: {
      bind_host: "0.0.0.0",
    },
    autoRunAfterPlan: false,
    programSettings: {
      developer_mode: false,
    },
    planDraft: {
      project_prompt: "Ship the UI",
      execution_mode: "serial",
      closeout_status: "not_started",
      steps: [
        {
          step_id: "ST1",
          title: "Plan",
          display_description: "Prepare the flow",
          codex_description: "Prepare the flow",
          success_criteria: "Flow exists",
          reasoning_effort: "medium",
          status: "completed",
        },
        {
          step_id: "ST2",
          title: "Build",
          display_description: "Build the screen",
          codex_description: "Build the screen",
          success_criteria: "Screen renders",
          reasoning_effort: "high",
          status: "pending",
        },
      ],
    },
    selectedStepId: "ST2",
    modelPresets: [],
    modelCatalog: [],
    busy: false,
    onChangeForm: noop,
    onChangeProgramSettings: noop,
    onChooseDirectory: noop,
    onArchiveProject: noop,
    onDeleteProject: noop,
    onDeleteHistoryEntry: noop,
    onGenerateShareLink: noop,
    onCopyShareLink: noop,
    onRevokeShareLink: noop,
    onChangeShareSettings: noop,
    onChangeAutoRunAfterPlan: noop,
    onPromptChange: noop,
    onGeneratePlan: noop,
    onSavePlan: noop,
    onResetPlan: noop,
    onRunPlan: noop,
    onRunCloseout: noop,
    onRequestStop: noop,
    onSelectStep: noop,
    onUpdateStepField: noop,
    onSaveStepLocal: noop,
    onAddStep: noop,
    onDeleteStep: noop,
    onMoveStep: noop,
    activeJob: null,
    ...overrides,
  };
}

test("ParallelRunControlView shows the auto-run toggle as off by default", async () => {
  const html = await renderBundledComponent(
    "parallel-run-control-auto-run-render",
    "./src/components/views/ParallelRunControlView.jsx",
    "ParallelRunControlView",
    {
      detail: {
        project: {
          current_status: "plan_ready",
        },
        runtime: {
          execution_mode: "parallel",
          effort: "medium",
        },
        runtime_insights: {
          execution: {
            remaining_seconds: 0,
          },
          parallel: {
            recommended_workers: 1,
            cpu_parallel_limit: 4,
            cpu_logical_count: 16,
            memory_parallel_limit: 4,
            memory_available_bytes: 8589934592,
          },
        },
      },
      planDraft: {
        project_prompt: "Ship the UI",
        execution_mode: "parallel",
        closeout_status: "not_started",
        steps: [
          {
            step_id: "ST1",
            title: "Build",
            display_description: "Build the screen",
            codex_description: "Build the screen",
            success_criteria: "Screen renders",
            reasoning_effort: "high",
            status: "pending",
          },
        ],
      },
      activeJob: null,
      autoRunAfterPlan: false,
      selectedStepId: "ST1",
      busy: false,
      onPromptChange: noop,
      onGeneratePlan: noop,
      onSavePlan: noop,
      onResetPlan: noop,
      onRunPlan: noop,
      onRequestStop: noop,
      onAutoRunAfterPlanChange: noop,
      onSelectStep: noop,
      onUpdateStepField: noop,
      onSaveStepLocal: noop,
      onAddStep: noop,
      onDeleteStep: noop,
    },
  );

  assert.match(html, /Auto-run After Plan/);
  assert.match(html, /type="checkbox"/);
  assert.doesNotMatch(html, /checked=""/);  // checkbox should be unchecked
});

test("ParallelRunControlView renders queued reservations with cancellation controls", async () => {
  const html = await renderBundledComponent(
    "parallel-run-control-reservations-render",
    "./src/components/views/ParallelRunControlView.jsx",
    "ParallelRunControlView",
    {
      detail: {
        project: {
          current_status: "plan_ready",
        },
        runtime: {
          execution_mode: "parallel",
          effort: "medium",
        },
        runtime_insights: {
          execution: {
            remaining_seconds: 120,
          },
          parallel: {
            recommended_workers: 1,
            cpu_parallel_limit: 4,
            cpu_logical_count: 16,
            memory_parallel_limit: 4,
            memory_available_bytes: 8589934592,
          },
        },
      },
      planDraft: {
        project_prompt: "Ship the UI",
        execution_mode: "parallel",
        closeout_status: "not_started",
        steps: [
          {
            step_id: "ST1",
            title: "Build",
            display_description: "Build the screen",
            codex_description: "Build the screen",
            success_criteria: "Screen renders",
            reasoning_effort: "high",
            status: "pending",
          },
        ],
      },
      activeJob: {
        id: "job-1",
        status: "queued",
        command: "run-plan",
        queue_position: 1,
      },
      queuedJobs: [
        {
          id: "job-1",
          status: "queued",
          command: "run-plan",
          queue_position: 1,
          project_dir: "C:/work/repo-a",
        },
        {
          id: "job-2",
          status: "queued",
          command: "generate-plan",
          queue_position: 2,
          project_dir: "C:/work/repo-b",
        },
      ],
      autoRunAfterPlan: false,
      selectedStepId: "ST1",
      busy: true,
      canCancelReservation: true,
      onPromptChange: noop,
      onGeneratePlan: noop,
      onSavePlan: noop,
      onResetPlan: noop,
      onRunPlan: noop,
      onRequestStop: noop,
      onCancelQueuedJob: noop,
      onAutoRunAfterPlanChange: noop,
      onSelectStep: noop,
      onUpdateStepField: noop,
      onSaveStepLocal: noop,
      onAddStep: noop,
      onDeleteStep: noop,
    },
  );

  assert.match(html, /Reservations/);
  assert.match(html, /#1/);
  assert.match(html, /repo-a/);
  assert.match(html, /Cancel Reservation/);
});

test("ParallelRunControlView keeps reset available while generate-plan is running", async () => {
  const html = await renderBundledComponent(
    "parallel-run-control-reset-during-planning-render",
    "./src/components/views/ParallelRunControlView.jsx",
    "ParallelRunControlView",
    {
      detail: {
        project: {
          current_status: "setup_ready",
        },
        runtime: {
          execution_mode: "parallel",
          effort: "high",
        },
      },
      planDraft: {
        project_prompt: "Generate a new plan",
        execution_mode: "parallel",
        closeout_status: "not_started",
        steps: [],
      },
      activeJob: {
        id: "job-generate",
        status: "running",
        command: "generate-plan",
      },
      queuedJobs: [],
      autoRunAfterPlan: false,
      selectedStepId: "",
      busy: true,
      canCancelReservation: false,
      canRequestStop: true,
      onPromptChange: noop,
      onGeneratePlan: noop,
      onSavePlan: noop,
      onResetPlan: noop,
      onRunPlan: noop,
      onRequestStop: noop,
      onCancelQueuedJob: noop,
      onAutoRunAfterPlanChange: noop,
      onSelectStep: noop,
      onUpdateStepField: noop,
      onSaveStepLocal: noop,
      onAddStep: noop,
      onDeleteStep: noop,
    },
  );

  assert.match(html, />Reset<\/span>/);
  // Verify the Reset button is NOT disabled: extract its button tag and check
  const resetMatch = html.match(/<button[^>]*>(?:<[^>]*>)*<span>Reset<\/span><\/button>/);
  assert.ok(resetMatch, "Reset button should exist");
  assert.doesNotMatch(resetMatch[0], /disabled=""/);
});

test("CenterWorkspace upgrades legacy serial plans into the parallel execution tree view", async () => {
  const html = await renderBundledComponent(
    "center-workspace-render",
    "./src/components/layout/CenterWorkspace.jsx",
    "CenterWorkspace",
    baseWorkspaceProps(),
  );

  assert.match(html, /run-flow-area/);
  assert.match(html, /<svg/);
  assert.match(html, /CO1/);
  assert.doesNotMatch(html, /Serial/);
});

test("CenterWorkspace renders the parallel execution flow chart for parallel plans", async () => {
  const html = await renderBundledComponent(
    "parallel-workspace-render",
    "./src/components/layout/CenterWorkspace.jsx",
    "CenterWorkspace",
    baseWorkspaceProps({
      detail: {
        project: {
          current_status: "plan_ready",
        },
        runtime: {
          execution_mode: "parallel",
          effort: "medium",
        },
        runtime_insights: {
          parallel: {
            recommended_workers: 1,
            cpu_parallel_limit: 4,
            cpu_logical_count: 16,
            memory_parallel_limit: 1,
            memory_available_bytes: 2218209280,
          },
        },
      },
      form: {
        runtime: {
          execution_mode: "parallel",
        },
      },
      planDraft: {
        project_prompt: "Ship the UI",
        execution_mode: "parallel",
        closeout_status: "not_started",
        steps: [
          {
            step_id: "ST1",
            title: "Split work",
            display_description: "Prepare the DAG",
            codex_description: "Prepare the DAG",
            success_criteria: "DAG exists",
            reasoning_effort: "medium",
            depends_on: [],
            owned_paths: ["src/jakal_flow/planning.py"],
            status: "completed",
          },
          {
            step_id: "ST2",
            title: "Desktop",
            display_description: "Render the desktop flow",
            codex_description: "Render the desktop flow",
            success_criteria: "Desktop flow renders",
            reasoning_effort: "high",
            depends_on: ["ST1"],
            owned_paths: ["desktop/src"],
            status: "pending",
          },
          {
            step_id: "ST3",
            title: "Backend",
            display_description: "Update the backend",
            codex_description: "Update the backend",
            success_criteria: "Backend saves the DAG",
            reasoning_effort: "high",
            depends_on: ["ST1"],
            owned_paths: ["src/jakal_flow"],
            status: "pending",
          },
        ],
      },
      selectedStepId: "ST2",
    }),
  );

  assert.match(html, /run-flow-area/);
  assert.match(html, /<svg/);
  assert.match(html, /Ready Nodes/);
  assert.match(html, /Depends On/);
  assert.match(html, /Owned Paths/);
  assert.match(html, /Parallel Limit/);
  assert.doesNotMatch(html, /Not started/);
  assert.doesNotMatch(html, /src\/jakal_flow/);
  assert.match(html, /CO1/);
  assert.doesNotMatch(html, /Layer 1/);
});

test("CenterWorkspace keeps the step editor hidden until a block is selected", async () => {
  const html = await renderBundledComponent(
    "parallel-workspace-no-selection-render",
    "./src/components/layout/CenterWorkspace.jsx",
    "CenterWorkspace",
    baseWorkspaceProps({
      selectedStepId: "",
    }),
  );

  assert.doesNotMatch(html, /Depends On/);
  assert.doesNotMatch(html, /Owned Paths/);
  assert.doesNotMatch(html, /Save Local/);
});

test("RightSidebarPane renders the project chat on the right rail by default", async () => {
  const html = await renderBundledComponent(
    "right-sidebar-chat-render",
    "./src/components/layout/RightSidebarPane.jsx",
    "RightSidebarPane",
    {
      detail: {
        project: {
          current_status: "plan_ready",
        },
        runtime: {
          effort: "medium",
        },
      },
      planDraft: {
        steps: [],
      },
      selectedStepId: "",
      modelPresets: [],
      modelCatalog: [
        {
          model: "gpt-5.4-mini",
          display_name: "GPT-5.4 Mini",
          hidden: false,
          provider: "openai",
        },
      ],
      form: {
        runtime: {
          generate_word_report: false,
        },
      },
      activeJob: null,
      busy: false,
      chat: {
        sessions: [
          { session_id: "chat-1", title: "Release", message_count: 2 },
        ],
        active_session_id: "chat-1",
        messages: [
          { message_id: "msg-1", role: "assistant", text: "Hello from the right side." },
        ],
        summary_file: "C:/demo/chat.summary.txt",
      },
      chatSettings: {
        chat_model_provider: "openai",
        chat_model: "gpt-5.4-mini",
      },
      selectedChatSessionId: "chat-1",
      chatDraftSession: false,
      onChangeForm: noop,
      onSelectChatSession: noop,
      onStartNewChatSession: noop,
      onSendChatMessage: noop,
      onChangeChatModelSelection: noop,
    },
  );

  assert.match(html, /AI Chat/);
  assert.match(html, /Chat model/);
  assert.match(html, /GPT-5\.4 Mini · OpenAI/);
  assert.match(html, /Release/);
  assert.match(html, /Hello from the right side\./);
  assert.match(html, /chat\.summary\.txt/);
});

test("RightSidebarPane keeps the icon rail visible when the right panel is collapsed", async () => {
  const html = await renderBundledComponent(
    "right-sidebar-collapsed-rail-render",
    "./src/components/layout/RightSidebarPane.jsx",
    "RightSidebarPane",
    {
      collapsed: true,
      activeTab: "chat",
      detail: {
        project: {
          current_status: "plan_ready",
        },
      },
      planDraft: {
        steps: [],
      },
      selectedStepId: "",
      modelPresets: [],
      modelCatalog: [],
      form: {
        runtime: {
          generate_word_report: false,
        },
      },
      activeJob: null,
      busy: false,
      chat: {
        messages: [
          { message_id: "msg-1", role: "assistant", text: "Hello from the right side." },
        ],
      },
      onChangeForm: noop,
      onSelectChatSession: noop,
      onStartNewChatSession: noop,
      onSendChatMessage: noop,
      onChangeChatModelSelection: noop,
    },
  );

  assert.match(html, /rsb--collapsed/);
  assert.match(html, /title="AI Chat"/);
  assert.doesNotMatch(html, /Chat model/);
  assert.doesNotMatch(html, /Hello from the right side\./);
});

test("RightSidebarPane renders assistant replies with safe markdown while keeping user text plain", async () => {
  const html = await renderBundledComponent(
    "right-sidebar-chat-markdown-render",
    "./src/components/layout/RightSidebarPane.jsx",
    "RightSidebarPane",
    {
      detail: {
        project: {
          current_status: "plan_ready",
        },
        runtime: {
          effort: "medium",
        },
      },
      planDraft: {
        steps: [],
      },
      selectedStepId: "",
      modelPresets: [],
      modelCatalog: [],
      form: {
        runtime: {
          generate_word_report: false,
        },
      },
      activeJob: null,
      busy: false,
      chat: {
        sessions: [
          { session_id: "chat-1", title: "Markdown", message_count: 2 },
        ],
        active_session_id: "chat-1",
        messages: [
          {
            message_id: "msg-1",
            role: "assistant",
            text: "# Release Notes\n\n- Ship UI polish\n- Keep code blocks\n\n```js\nconst ready = true;\n  return ready;\n```\n\nOpen the [preview](https://example.com).",
          },
          {
            message_id: "msg-2",
            role: "user",
            text: "Keep **this** plain.\n  Preserve the indent.",
          },
        ],
        summary_file: "C:/demo/chat.summary.txt",
      },
      chatSettings: {},
      selectedChatSessionId: "chat-1",
      chatDraftSession: false,
      onChangeForm: noop,
      onSelectChatSession: noop,
      onStartNewChatSession: noop,
      onSendChatMessage: noop,
      onChangeChatModelSelection: noop,
    },
  );

  assert.match(html, /sidebar-chat-bubble__content--markdown/);
  assert.match(html, /<h1 class="sidebar-chat-markdown__heading">Release Notes<\/h1>/);
  assert.match(html, /<ul class="sidebar-chat-markdown__list">/);
  assert.match(html, /<li>Ship UI polish<\/li>/);
  assert.match(html, /<pre class="sidebar-chat-markdown__pre"><code class="language-js">const ready = true;/);
  assert.match(html, /href="https:\/\/example\.com"/);
  assert.match(html, /sidebar-chat-bubble__content--plain/);
  assert.match(html, /Keep \*\*this\*\* plain\./);
  assert.doesNotMatch(html, /<strong>this<\/strong>/);
});

test("CenterWorkspace shows estimated cost only for paid configured runtimes", async () => {
  const html = await renderBundledComponent(
    "parallel-workspace-paid-cost-render",
    "./src/components/layout/CenterWorkspace.jsx",
    "CenterWorkspace",
    baseWorkspaceProps({
      detail: {
        project: {
          current_status: "running:parallel",
        },
        runtime: {
          execution_mode: "parallel",
          effort: "medium",
          billing_mode: "token",
          model_provider: "openrouter",
        },
        runtime_insights: {
          execution: {
            remaining_seconds: 90,
          },
          cost: {
            estimated_total_cost_usd: 1.23,
            recent: {
              billing_mode: "token",
              configured: true,
              estimated_cost_usd: 0.45,
            },
            remaining: {
              billing_mode: "token",
              configured: true,
              estimated_cost_usd: 0.78,
            },
          },
          parallel: {
            recommended_workers: 1,
            cpu_parallel_limit: 4,
            cpu_logical_count: 16,
            memory_parallel_limit: 1,
            memory_available_bytes: 2218209280,
          },
        },
        plan: {
          project_prompt: "Ship the paid flow",
          execution_mode: "parallel",
          closeout_status: "running",
          steps: [
            { step_id: "ST1", title: "Plan", status: "completed" },
            { step_id: "ST2", title: "Build", status: "running", depends_on: ["ST1"], owned_paths: ["desktop/src"] },
          ],
        },
      },
      planDraft: {
        project_prompt: "Ship the paid flow",
        execution_mode: "parallel",
        closeout_status: "running",
        steps: [
          { step_id: "ST1", title: "Plan", status: "completed" },
          { step_id: "ST2", title: "Build", status: "running", depends_on: ["ST1"], owned_paths: ["desktop/src"] },
        ],
      },
      selectedStepId: "ST2",
      busy: true,
      activeJob: {
        status: "running",
        command: "run-plan",
      },
    }),
  );

  assert.match(html, /\$1\.23/);
  assert.match(html, /Closeout[\s\S]*Running/);
});

test("CenterWorkspace prefers the live detail plan while a run is active", async () => {
  const html = await renderBundledComponent(
    "parallel-workspace-live-plan-render",
    "./src/components/layout/CenterWorkspace.jsx",
    "CenterWorkspace",
    baseWorkspaceProps({
      detail: {
        project: {
          current_status: "running:parallel",
        },
        runtime: {
          execution_mode: "parallel",
          effort: "medium",
        },
        plan: {
          project_prompt: "Ship the live UI",
          execution_mode: "parallel",
          closeout_status: "not_started",
          steps: [
            { step_id: "ST1", title: "Plan", status: "completed" },
            { step_id: "ST2", title: "Build", status: "running", depends_on: ["ST1"], owned_paths: ["desktop/src"] },
            { step_id: "ST3", title: "Backend", status: "running", depends_on: ["ST1"], owned_paths: ["src/jakal_flow"] },
          ],
        },
      },
      planDraft: {
        project_prompt: "Ship the stale UI",
        execution_mode: "parallel",
        closeout_status: "not_started",
        steps: [
          { step_id: "ST1", title: "Plan", status: "completed" },
          { step_id: "ST2", title: "Build", status: "pending", depends_on: ["ST1"], owned_paths: ["desktop/src"] },
          { step_id: "ST3", title: "Backend", status: "pending", depends_on: ["ST1"], owned_paths: ["src/jakal_flow"] },
        ],
      },
      selectedStepId: "ST2",
      busy: true,
      activeJob: {
        status: "running",
        command: "run-plan",
      },
    }),
  );

  const runningNodeMatches = html.match(/execution-flow-chart__node--info/g) || [];
  assert.match(html, /Running: Parallel/);
  assert.match(html, /Ship the live UI/);
  assert.equal(runningNodeMatches.length, 2);
});

test("CenterWorkspace shows debugging badges in yellow while debugger recovery is active", async () => {
  const html = await renderBundledComponent(
    "parallel-workspace-debugging-render",
    "./src/components/layout/CenterWorkspace.jsx",
    "CenterWorkspace",
    baseWorkspaceProps({
      detail: {
        project: {
          current_status: "running:debugging",
        },
        runtime: {
          execution_mode: "parallel",
          effort: "medium",
        },
        plan: {
          project_prompt: "Recover the flow",
          execution_mode: "parallel",
          closeout_status: "not_started",
          steps: [
            { step_id: "ST1", title: "Plan", status: "completed" },
            { step_id: "ST2", title: "Build", status: "running", depends_on: ["ST1"], owned_paths: ["desktop/src"] },
            { step_id: "ST3", title: "Backend", status: "pending", depends_on: ["ST1"], owned_paths: ["src/jakal_flow"] },
          ],
        },
      },
      planDraft: {
        project_prompt: "Recover the stale flow",
        execution_mode: "parallel",
        closeout_status: "not_started",
        steps: [
          { step_id: "ST1", title: "Plan", status: "completed" },
          { step_id: "ST2", title: "Build", status: "pending", depends_on: ["ST1"], owned_paths: ["desktop/src"] },
          { step_id: "ST3", title: "Backend", status: "pending", depends_on: ["ST1"], owned_paths: ["src/jakal_flow"] },
        ],
      },
      selectedStepId: "ST2",
      busy: true,
      activeJob: {
        status: "running",
        command: "run-plan",
      },
    }),
  );

  assert.match(html, /Debugging/);
  assert.match(html, /status-badge--warning">Debugging<\/span>/);
  assert.match(html, /execution-flow-chart__node--warning/);
});

test("IdeToolbar renders the active command and DAG-ready progress text", async () => {
  const html = await renderBundledComponent(
    "ide-toolbar-render",
    "./src/components/layout/IdeToolbar.jsx",
    "IdeToolbar",
    {
    projectDetail: {
      project: {
        display_name: "Demo",
        current_status: "plan_ready",
      },
    },
    planDraft: {
      execution_mode: "parallel",
      closeout_status: "not_started",
      steps: [
        { step_id: "ST1", status: "completed" },
        { step_id: "ST2", status: "pending", depends_on: ["ST1"], owned_paths: ["desktop/src"] },
        { step_id: "ST3", status: "pending", depends_on: ["ST1"], owned_paths: ["src/jakal_flow"] },
      ],
    },
    busy: true,
    activeJob: {
      status: "running",
      command: "run-plan",
    },
    activeCenterTab: "run",
    onRefresh: noop,
    onOpenSettings: noop,
    onGeneratePlan: noop,
    onRunPlan: noop,
    onRunCloseout: noop,
    onApproveCheckpoint: noop,
  });

  assert.match(html, /Run Remaining Steps/);
  assert.match(html, /Completed 1\/4 steps, ready: ST2, ST3/);
  assert.match(html, /Program Settings/);
  assert.doesNotMatch(html, />Closeout<\/button>/);
});

test("IdeToolbar renders the selected project and highlights program settings", async () => {
  const html = await renderBundledComponent(
    "ide-toolbar-project-selector-render",
    "./src/components/layout/IdeToolbar.jsx",
    "IdeToolbar",
    {
      projects: [
        {
          repo_id: "demo",
          display_name: "Demo Project",
          status: "plan_ready",
        },
      ],
      selectedProjectId: "demo",
      projectDetail: {
        project: {
          display_name: "Demo Project",
          current_status: "plan_ready",
        },
      },
      planDraft: {
        execution_mode: "serial",
        closeout_status: "not_started",
        steps: [],
      },
      busy: false,
      activeJob: null,
      activeCenterTab: "app-settings",
      onSelectProject: noop,
      onNewProject: noop,
      onRefresh: noop,
      onOpenSettings: noop,
      onGeneratePlan: noop,
      onRunPlan: noop,
      onApproveCheckpoint: noop,
    },
  );

  assert.match(html, /Demo Project/);
  assert.match(html, /toolbar-btn toolbar-btn--active/);
  assert.match(html, /title="Program Settings"/);
});

test("IdeToolbar exposes a right sidebar toggle and keeps it active while the inspector is open", async () => {
  const html = await renderBundledComponent(
    "ide-toolbar-right-sidebar-toggle-render",
    "./src/components/layout/IdeToolbar.jsx",
    "IdeToolbar",
    {
      projects: [],
      selectedProjectId: "",
      projectDetail: {
        project: {
          current_status: "plan_ready",
        },
      },
      planDraft: {
        execution_mode: "serial",
        closeout_status: "not_started",
        steps: [],
      },
      busy: false,
      activeJob: null,
      activeCenterTab: "run",
      rightCollapsed: false,
      onSelectProject: noop,
      onNewProject: noop,
      onRefresh: noop,
      onOpenSettings: noop,
      onToggleRight: noop,
      onGeneratePlan: noop,
      onRunPlan: noop,
      onApproveCheckpoint: noop,
    },
  );

  assert.match(html, /title="Toggle right sidebar"/);
  assert.match(html, /title="Toggle right sidebar"[\s\S]*title="Toggle right sidebar"/);
  assert.match(html, /toolbar-btn toolbar-btn--icon toolbar-btn--active/);
});

test("IdeToolbar keeps project link actions visible when only form-level paths are available", async () => {
  const html = await renderBundledComponent(
    "ide-toolbar-project-links-render",
    "./src/components/layout/IdeToolbar.jsx",
    "IdeToolbar",
    {
      projects: [],
      selectedProjectId: "",
      projectDetail: {
        project: {
          current_status: "setup_ready",
        },
      },
      planDraft: {
        execution_mode: "serial",
        closeout_status: "not_started",
        steps: [],
      },
      projectPath: "C:/demo",
      githubUrl: "https://github.com/example/demo",
      busy: false,
      activeJob: null,
      activeCenterTab: "config",
      onSelectProject: noop,
      onNewProject: noop,
      onRefresh: noop,
      onOpenSettings: noop,
      onGeneratePlan: noop,
      onRunPlan: noop,
      onApproveCheckpoint: noop,
      onOpenFolder: noop,
      onOpenVsCode: noop,
      onOpenGithub: noop,
    },
  );

  assert.match(html, /title="Open folder"/);
  assert.match(html, /title="Open in external editor"/);
  assert.match(html, /title="Open on GitHub"/);
});

test("IdeToolbar keeps project link actions visible but disabled without project paths", async () => {
  const html = await renderBundledComponent(
    "ide-toolbar-project-links-disabled-render",
    "./src/components/layout/IdeToolbar.jsx",
    "IdeToolbar",
    {
      projects: [],
      selectedProjectId: "",
      projectDetail: {
        project: {
          current_status: "idle",
        },
      },
      planDraft: {
        execution_mode: "serial",
        closeout_status: "not_started",
        steps: [],
      },
      projectPath: "",
      githubUrl: "",
      busy: false,
      activeJob: null,
      activeCenterTab: "config",
      onSelectProject: noop,
      onNewProject: noop,
      onRefresh: noop,
      onOpenSettings: noop,
      onGeneratePlan: noop,
      onRunPlan: noop,
      onApproveCheckpoint: noop,
      onOpenFolder: noop,
      onOpenVsCode: noop,
      onOpenGithub: noop,
    },
  );

  assert.match(html, /title="Open folder"[^>]*disabled=""/);
  assert.match(html, /title="Open in external editor"[^>]*disabled=""/);
  assert.match(html, /title="Open on GitHub"[^>]*disabled=""/);
});

test("IdeToolbar prefers the live plan progress while a run is active", async () => {
  const html = await renderBundledComponent(
    "ide-toolbar-live-plan-render",
    "./src/components/layout/IdeToolbar.jsx",
    "IdeToolbar",
    {
      projectDetail: {
        project: {
          display_name: "Demo",
          current_status: "running:parallel",
        },
        plan: {
          execution_mode: "parallel",
          closeout_status: "not_started",
          steps: [
            { step_id: "ST1", status: "completed" },
            { step_id: "ST2", status: "running", depends_on: ["ST1"], owned_paths: ["desktop/src"] },
            { step_id: "ST3", status: "running", depends_on: ["ST1"], owned_paths: ["src/jakal_flow"] },
          ],
        },
      },
      planDraft: {
        execution_mode: "parallel",
        closeout_status: "not_started",
        steps: [
          { step_id: "ST1", status: "completed" },
          { step_id: "ST2", status: "pending", depends_on: ["ST1"], owned_paths: ["desktop/src"] },
          { step_id: "ST3", status: "pending", depends_on: ["ST1"], owned_paths: ["src/jakal_flow"] },
        ],
      },
      busy: true,
      activeJob: {
        status: "running",
        command: "run-plan",
      },
      activeCenterTab: "run",
      onRefresh: noop,
      onOpenSettings: noop,
      onGeneratePlan: noop,
      onRunPlan: noop,
      onRunCloseout: noop,
      onApproveCheckpoint: noop,
    },
  );

  assert.match(html, /Completed 1\/4 steps, running: ST2, ST3/);
});

test("IdeToolbar shows planning progress while plan generation is active", async () => {
  const html = await renderBundledComponent(
    "ide-toolbar-planning-progress-render",
    "./src/components/layout/IdeToolbar.jsx",
    "IdeToolbar",
    {
      projectDetail: {
        project: {
          display_name: "Demo",
          current_status: "setup_ready",
        },
        planning_progress: {
          stage_count: 4,
          current_stage_index: 2,
          current_stage_status: "running",
        },
      },
      planDraft: {
        execution_mode: "serial",
        closeout_status: "not_started",
        steps: [],
      },
      busy: true,
      activeJob: {
        status: "running",
        command: "generate-plan",
      },
      activeCenterTab: "run",
      onRefresh: noop,
      onOpenSettings: noop,
      onGeneratePlan: noop,
      onRunPlan: noop,
      onRunCloseout: noop,
      onApproveCheckpoint: noop,
    },
  );

  assert.match(html, /Planning stage 2\/4, Running/);
  assert.doesNotMatch(html, /No plan yet/);
});

test("IdeToolbar still shows planning progress when planning events exist before the active job snapshot arrives", async () => {
  const html = await renderBundledComponent(
    "ide-toolbar-planning-progress-without-job-render",
    "./src/components/layout/IdeToolbar.jsx",
    "IdeToolbar",
    {
      projectDetail: {
        project: {
          display_name: "Demo",
          current_status: "setup_ready",
        },
        planning_progress: {
          stage_count: 4,
          current_stage_index: 2,
          current_stage_status: "running",
        },
      },
      planDraft: {
        execution_mode: "serial",
        closeout_status: "not_started",
        steps: [],
      },
      busy: false,
      activeJob: null,
      activeCenterTab: "run",
      onRefresh: noop,
      onOpenSettings: noop,
      onGeneratePlan: noop,
      onRunPlan: noop,
      onRunCloseout: noop,
      onApproveCheckpoint: noop,
    },
  );

  assert.match(html, /Planning stage 2\/4, Running/);
});

test("IdeToolbar exposes checkpoint approval when a checkpoint is waiting for review", async () => {
  const html = await renderBundledComponent(
    "ide-toolbar-pending-checkpoint-render",
    "./src/components/layout/IdeToolbar.jsx",
    "IdeToolbar",
    {
      projectDetail: {
        project: {
          display_name: "Demo",
          current_status: "awaiting_checkpoint_approval",
        },
      },
      pendingCheckpoint: {
        checkpoint_id: "CP2",
        status: "awaiting_review",
      },
      planDraft: {
        execution_mode: "serial",
        closeout_status: "not_started",
        steps: [
          { step_id: "ST1", status: "completed" },
          { step_id: "ST2", status: "pending" },
        ],
      },
      busy: false,
      activeJob: null,
      activeCenterTab: "run",
      onRefresh: noop,
      onOpenSettings: noop,
      onGeneratePlan: noop,
      onRunPlan: noop,
      onRunCloseout: noop,
      onApproveCheckpoint: noop,
    },
  );

  assert.match(html, /CP2/);
  assert.match(html, /Approve Checkpoint/);
});

test("IdeToolbar prioritizes the debugging status over the generic active command", async () => {
  const html = await renderBundledComponent(
    "ide-toolbar-debugging-render",
    "./src/components/layout/IdeToolbar.jsx",
    "IdeToolbar",
    {
    projectDetail: {
      project: {
        display_name: "Demo",
        current_status: "running:debugging",
      },
    },
    planDraft: {
      execution_mode: "serial",
      closeout_status: "not_started",
      steps: [
        { step_id: "ST1", status: "completed" },
        { step_id: "ST2", status: "running" },
      ],
    },
    busy: true,
    activeJob: {
      status: "running",
      command: "run-plan",
    },
    activeCenterTab: "run",
    onRefresh: noop,
    onOpenSettings: noop,
    onGeneratePlan: noop,
    onRunPlan: noop,
    onRunCloseout: noop,
    onApproveCheckpoint: noop,
  });

  assert.match(html, /Debugging/);
});

test("AppSettingsView omits the removed subsection helper copy", async () => {
  const html = await renderBundledComponent(
    "app-settings-render",
    "./src/components/views/AppSettingsView.jsx",
    "AppSettingsView",
    {
      settings: {
        ui_theme: "dark",
        developer_mode: false,
        model_provider: "openai",
        local_model_provider: "ollama",
        dashboard_visibility: {},
      },
      shareSettings: {
        bind_host: "0.0.0.0",
      },
      shareDetail: null,
      busy: false,
      onChangeSettings: noop,
      onGenerateShareLink: noop,
      onCopyShareLink: noop,
      onRevokeShareLink: noop,
      onChangeShareSettings: noop,
    },
  );

  assert.doesNotMatch(html, /These preferences affect the desktop shell itself\./);
  assert.doesNotMatch(html, /Show only the dashboard cards you want to keep visible\./);
  assert.doesNotMatch(html, /These defaults are reused across projects unless a project-specific field replaces them\./);
  assert.match(html, /Application/);
  assert.match(html, /Dashboard/);
  assert.match(html, /Execution/);
  assert.match(html, /Share/);
});

test("RunProgressPanel renders current work, progress, and recent activity", async () => {
  const html = await renderBundledComponent(
    "run-progress-panel-render",
    "./src/components/layout/RunProgressPanel.jsx",
    "RunProgressPanel",
    {
    detail: {
      project: {
        current_status: "running:block:2",
      },
      activity: [
        "2026-03-26T09:01:00Z | step-started [ST3] | Running ST3: Build the backend",
      ],
      plan: {
        execution_mode: "parallel",
        closeout_status: "not_started",
        steps: [
          { step_id: "ST1", title: "Plan", status: "completed" },
          { step_id: "ST2", title: "Build", status: "running", depends_on: ["ST1"], owned_paths: ["desktop/src"] },
          { step_id: "ST3", title: "Backend", status: "running", depends_on: ["ST1"], owned_paths: ["src/jakal_flow"] },
        ],
      },
      stats: {
        total_steps: 3,
        completed_steps: 1,
        failed_steps: 0,
        running_steps: 2,
        remaining_steps: 2,
      },
    },
    planDraft: {
      execution_mode: "parallel",
      closeout_status: "not_started",
      steps: [
        { step_id: "ST1", title: "Plan", status: "completed" },
        { step_id: "ST2", title: "Build", status: "running", depends_on: ["ST1"], owned_paths: ["desktop/src"] },
        { step_id: "ST3", title: "Backend", status: "running", depends_on: ["ST1"], owned_paths: ["src/jakal_flow"] },
      ],
    },
    activeJob: {
      status: "running",
      command: "run-plan",
    },
  });

  assert.match(html, /Live Run/);
  assert.match(html, /Working on ST2 .+ Build, ST3 .+ Backend/);
  assert.match(html, /Completed 1\/4 steps, running: ST2, ST3/);
  assert.match(html, /2 node\(s\) running/);
  assert.match(html, /Running ST3: Build the backend/);
});

test("RunProgressPanel renders debugging state from the project status", async () => {
  const html = await renderBundledComponent(
    "run-progress-panel-debugging-render",
    "./src/components/layout/RunProgressPanel.jsx",
    "RunProgressPanel",
    {
    detail: {
      project: {
        current_status: "running:debugging",
      },
      activity: [
        "debugger | debugger_invoked | Debugging ST2 - Build | python -m pytest exited with 1",
      ],
      plan: {
        execution_mode: "serial",
        closeout_status: "not_started",
        steps: [
          { step_id: "ST1", title: "Plan", status: "completed" },
          { step_id: "ST2", title: "Build", status: "running" },
        ],
      },
      stats: {
        total_steps: 2,
        completed_steps: 1,
        failed_steps: 0,
        running_steps: 1,
        remaining_steps: 1,
      },
    },
    planDraft: {
      execution_mode: "serial",
      closeout_status: "not_started",
      steps: [
        { step_id: "ST1", title: "Plan", status: "completed" },
        { step_id: "ST2", title: "Build", status: "running" },
      ],
    },
    activeJob: {
      status: "running",
      command: "run-plan",
    },
  });

  assert.match(html, /Debugging/);
  assert.match(html, /python -m pytest exited with 1/);
  assert.doesNotMatch(html, /Working on ST2 - Build/);
});

test("RunProgressPanel renders structured planning progress and stage chips", async () => {
  const html = await renderBundledComponent(
    "run-progress-panel-planning-render",
    "./src/components/layout/RunProgressPanel.jsx",
    "RunProgressPanel",
    {
      detail: {
        project: {
          current_status: "setup_ready",
        },
        activity: [
          "2026-03-26T09:02:00Z | planner-agent-started | Planner Agent A is decomposing the work into implementation blocks.",
        ],
        planning_progress: {
          stage_count: 4,
          completed_stages: 1,
          percent: 38,
          current_stage_key: "planner_a",
          current_stage_index: 2,
          current_stage_label: "Planner Agent A",
          current_stage_status: "running",
          current_agent_label: "Planner Agent A",
          message: "Planner Agent A is decomposing the work into implementation blocks.",
          stages: [
            { key: "context_scan", index: 1, label: "Scan repository context", status: "completed" },
            { key: "planner_a", index: 2, label: "Planner Agent A", status: "running", agent_label: "Planner Agent A" },
            { key: "planner_b", index: 3, label: "Planner Agent B", status: "pending" },
            { key: "finalize", index: 4, label: "Validate and save plan", status: "pending" },
          ],
        },
        plan: {
          execution_mode: "serial",
          closeout_status: "not_started",
          steps: [],
        },
        stats: {
          total_steps: 0,
          completed_steps: 0,
          failed_steps: 0,
          running_steps: 0,
          remaining_steps: 0,
        },
      },
      planDraft: {
        execution_mode: "serial",
        closeout_status: "not_started",
        steps: [],
      },
      activeJob: {
        status: "running",
        command: "generate-plan",
      },
    },
  );

  assert.match(html, /Planner Agent A/);
  assert.match(html, /Planning stage 2\/4, Running/);
  assert.match(html, /38%/);
  assert.match(html, /Scan repository context/);
  assert.match(html, /Validate and save plan/);
  assert.match(html, /Running/);
});

test("RunProgressPanel keeps planning progress visible when the bridge job snapshot is temporarily absent", async () => {
  const html = await renderBundledComponent(
    "run-progress-panel-planning-without-job-render",
    "./src/components/layout/RunProgressPanel.jsx",
    "RunProgressPanel",
    {
      detail: {
        project: {
          current_status: "setup_ready",
        },
        planning_progress: {
          stage_count: 4,
          completed_stages: 1,
          percent: 38,
          current_stage_key: "planner_a",
          current_stage_index: 2,
          current_stage_label: "Planner Agent A",
          current_stage_status: "running",
          current_agent_label: "Planner Agent A",
          message: "Planner Agent A is decomposing the work into implementation blocks.",
          stages: [
            { key: "context_scan", index: 1, label: "Scan repository context", status: "completed" },
            { key: "planner_a", index: 2, label: "Planner Agent A", status: "running", agent_label: "Planner Agent A" },
            { key: "planner_b", index: 3, label: "Planner Agent B", status: "pending" },
            { key: "finalize", index: 4, label: "Validate and save plan", status: "pending" },
          ],
        },
        plan: {
          execution_mode: "serial",
          closeout_status: "not_started",
          steps: [],
        },
      },
      planDraft: {
        execution_mode: "serial",
        closeout_status: "not_started",
        steps: [],
      },
      activeJob: null,
    },
  );

  assert.match(html, /Planning stage 2\/4, Running/);
  assert.match(html, /Planner Agent A/);
});

test("RunProgressPanel stays hidden while only a chat job is active", async () => {
  const html = await renderBundledComponent(
    "run-progress-panel-chat-hidden-render",
    "./src/components/layout/RunProgressPanel.jsx",
    "RunProgressPanel",
    {
      detail: {
        project: {
          current_status: "plan_ready",
        },
        plan: {
          execution_mode: "serial",
          closeout_status: "not_started",
          steps: [],
        },
        stats: {
          total_steps: 0,
          completed_steps: 0,
          failed_steps: 0,
          running_steps: 0,
          remaining_steps: 0,
        },
      },
      planDraft: {
        execution_mode: "serial",
        closeout_status: "not_started",
        steps: [],
      },
      activeJob: {
        status: "running",
        command: "send-chat-message",
      },
    },
  );

  assert.equal(html.trim(), "");
});

test("SidebarPane renders a filtered workspace tree without unrelated nodes", async () => {
  const html = await renderBundledComponent(
    "sidebar-pane-render",
    "./src/components/layout/SidebarPane.jsx",
    "SidebarPane",
    {
    activeTab: "workspace",
    onChangeTab: noop,
    projects: [],
    selectedProjectId: "",
    loadingProjectId: "",
    projectFilter: "",
    workspaceFilter: "bridge",
    onProjectFilterChange: noop,
    onWorkspaceFilterChange: noop,
    onSelectProject: noop,
    onNewProject: noop,
    onArchiveProject: noop,
    onDeleteProject: noop,
    onDeleteHistoryEntry: noop,
    onArchiveAllProjects: noop,
    onDeleteAllProjects: noop,
    workspaceTree: [
      {
        label: "Repository",
        path: "/repo",
        kind: "dir",
        children: [
          { label: "README.md", path: "/repo/README.md", kind: "file" },
          {
            label: "src",
            path: "/repo/src",
            kind: "dir",
            children: [
              { label: "ui_bridge.py", path: "/repo/src/ui_bridge.py", kind: "file" },
              { label: "planning.py", path: "/repo/src/planning.py", kind: "file" },
            ],
          },
        ],
      },
    ],
    checkpoints: { items: [] },
    github: {
      connected: false,
      origin_url: "",
      branch: "main",
      repo_url: "",
    },
  });

  assert.match(html, /ui_bridge\.py/);
  assert.match(html, /Repository/);
  assert.doesNotMatch(html, /README\.md/);
});

test("SidebarPane keeps a pending checkpoint visible and marked as live", async () => {
  const html = await renderBundledComponent(
    "sidebar-pane-pending-checkpoint-render",
    "./src/components/layout/SidebarPane.jsx",
    "SidebarPane",
    {
      activeTab: "plans",
      onChangeTab: noop,
      projects: [],
      selectedProjectId: "",
      loadingProjectId: "",
      projectFilter: "",
      workspaceFilter: "",
      onProjectFilterChange: noop,
      onWorkspaceFilterChange: noop,
      onSelectProject: noop,
      onNewProject: noop,
      onArchiveProject: noop,
      onDeleteProject: noop,
      onDeleteHistoryEntry: noop,
      onArchiveAllProjects: noop,
      onDeleteAllProjects: noop,
      workspaceTree: [],
      checkpoints: {
        items: [],
        pending: {
          checkpoint_id: "CP2",
          status: "awaiting_review",
          title: "Review the merged work",
          target_block: 2,
        },
      },
      github: {
        connected: false,
        origin_url: "",
        branch: "main",
        repo_url: "",
      },
    },
  );

  assert.match(html, /CP2/);
  assert.match(html, /Review the merged work/);
  assert.match(html, /sidebar-item--checkpoint-live/);
  assert.match(html, /status-badge--pulse/);
});

test("SidebarPane keeps only the new project action below the project search", async () => {
  const html = await renderBundledComponent(
    "sidebar-pane-project-actions-render",
    "./src/components/layout/SidebarPane.jsx",
    "SidebarPane",
    {
      activeTab: "projects",
      onChangeTab: noop,
      projects: [
        {
          repo_id: "demo",
          display_name: "Demo",
          status: "idle",
          detail: "Ready",
        },
      ],
      historyProjects: [],
      selectedProjectId: "demo",
      selectedHistoryId: "",
      loadingProjectId: "",
      projectFilter: "",
      workspaceFilter: "",
      onProjectFilterChange: noop,
      onWorkspaceFilterChange: noop,
      onSelectProject: noop,
      onSelectHistory: noop,
      onNewProject: noop,
      onArchiveProject: noop,
      onDeleteProject: noop,
      onDeleteHistoryEntry: noop,
      workspaceTree: [],
      checkpoints: { items: [] },
      github: {
        connected: false,
        origin_url: "",
        branch: "main",
        repo_url: "",
      },
    },
  );

  assert.doesNotMatch(html, />Archive All</);
  assert.doesNotMatch(html, />Delete All</);
  assert.match(html, /placeholder="Search projects"/);
  assert.match(html, /sidebar-search-wrapper[\s\S]*placeholder="Search projects"[\s\S]*sidebar-add-btn[\s\S]*>New</);
});

test("SidebarPane hides the content panel when no sidebar icon is active", async () => {
  const html = await renderBundledComponent(
    "sidebar-pane-collapsed-render",
    "./src/components/layout/SidebarPane.jsx",
    "SidebarPane",
    {
      activeTab: "",
      onChangeTab: noop,
      projects: [],
      historyProjects: [],
      selectedProjectId: "",
      selectedHistoryId: "",
      loadingProjectId: "",
      projectFilter: "",
      workspaceFilter: "",
      onProjectFilterChange: noop,
      onWorkspaceFilterChange: noop,
      onSelectProject: noop,
      onSelectHistory: noop,
      onNewProject: noop,
      onArchiveProject: noop,
      onDeleteProject: noop,
      onDeleteHistoryEntry: noop,
      workspaceTree: [],
      checkpoints: { items: [] },
      github: {
        connected: false,
        origin_url: "",
        branch: "main",
        repo_url: "",
      },
    },
  );

  assert.match(html, /sidebar-rail/);
  assert.doesNotMatch(html, /sidebar-panel/);
  assert.doesNotMatch(html, /Search projects/);
});

test("DashboardView hides cards that are disabled in program settings", async () => {
  const html = await renderBundledComponent(
    "dashboard-view-render",
    "./src/components/views/DashboardView.jsx",
    "DashboardView",
    {
      detail: {
        project: {
          display_name: "Demo",
          slug: "demo",
          current_status: "plan_ready",
          branch: "main",
          origin_url: "",
        },
        runtime: {
          execution_mode: "serial",
          model: "auto",
          effort: "medium",
        },
        snapshot: {
          recent_usage: {
            input_tokens: 12,
            output_tokens: 34,
          },
        },
        runtime_insights: {
          execution: {
            remaining_seconds: 90,
            estimated_total_seconds: 120,
          },
          cost: {
            estimated_total_cost_usd: 1.23,
            recent: {
              estimated_cost_usd: 0.45,
            },
          },
        },
        checkpoints: {
          pending: null,
        },
        codex_status: {
          account: {
            plan_type: "pro",
          },
          rate_limits: {
            items: [],
          },
          error: "",
        },
      },
      planDraft: {
        steps: [
          { step_id: "ST1", status: "completed" },
          { step_id: "ST2", status: "pending" },
        ],
      },
      form: {
        runtime: {
          generate_word_report: true,
        },
      },
      programSettings: {
        dashboard_visibility: {
          status: false,
          input_tokens: true,
          runtime_card: false,
          word_report_card: false,
        },
      },
      busy: false,
      modelPresets: [],
      modelCatalog: [],
      activeJob: null,
      onChangeForm: noop,
    },
  );

  assert.match(html, /Remaining Steps/);
  assert.match(html, /Input Tokens/);
  assert.match(html, /Estimated Remaining/);
  assert.match(html, /7d Usage/);
  assert.doesNotMatch(html, /5h Usage/);
  assert.doesNotMatch(html, /Status/);
  assert.doesNotMatch(html, /Runtime/);
  assert.doesNotMatch(html, /Closeout Report/);
});

test("DashboardView shows the parallel limit reason in the runtime card", async () => {
  const html = await renderBundledComponent(
    "dashboard-view-parallel-limit-render",
    "./src/components/views/DashboardView.jsx",
    "DashboardView",
    {
      detail: {
        project: {
          display_name: "Demo",
          slug: "demo",
          current_status: "running:parallel",
          branch: "main",
          origin_url: "",
        },
        runtime: {
          execution_mode: "parallel",
          model: "auto",
          effort: "medium",
        },
        snapshot: {
          recent_usage: {},
        },
        runtime_insights: {
          execution: {
            remaining_seconds: 90,
            estimated_total_seconds: 120,
          },
          cost: {
            estimated_total_cost_usd: 1.23,
            recent: {
              estimated_cost_usd: 0.45,
            },
          },
          parallel: {
            recommended_workers: 1,
            cpu_parallel_limit: 4,
            cpu_logical_count: 16,
            memory_parallel_limit: 1,
            memory_available_bytes: 2218209280,
          },
        },
        checkpoints: {
          pending: null,
        },
        codex_status: {
          account: {
            plan_type: "pro",
          },
          rate_limits: {
            items: [],
          },
          error: "",
        },
      },
      planDraft: {
        steps: [
          { step_id: "ST1", status: "completed" },
          { step_id: "ST2", status: "pending" },
          { step_id: "ST3", status: "pending" },
        ],
      },
      form: {
        runtime: {
          generate_word_report: true,
        },
      },
      programSettings: {
        dashboard_visibility: {
          status: true,
          remaining_steps: true,
          estimated_remaining: true,
          runtime_card: true,
          codex_usage_card: false,
          word_report_card: false,
        },
      },
      busy: false,
      modelPresets: [],
      modelCatalog: [],
      activeJob: null,
      onChangeForm: noop,
    },
  );

  assert.match(html, /Runtime/);
  assert.match(html, /Parallel Workers[\s\S]*1 worker/);
  assert.match(html, /Parallel Limit[\s\S]*Memory cap 1, CPU cap 4, free 2.1 GiB/);
});

test("DashboardView hides cost metrics for included billing", async () => {
  const html = await renderBundledComponent(
    "dashboard-view-included-billing-render",
    "./src/components/views/DashboardView.jsx",
    "DashboardView",
    {
      detail: {
        project: {
          display_name: "Demo",
          slug: "demo",
          current_status: "plan_ready",
          branch: "main",
          origin_url: "",
        },
        runtime: {
          execution_mode: "serial",
          model_provider: "openai",
          billing_mode: "included",
          model: "auto",
          effort: "medium",
        },
        snapshot: {
          recent_usage: {
            input_tokens: 12,
            output_tokens: 34,
          },
        },
        runtime_insights: {
          execution: {
            remaining_seconds: 90,
            estimated_total_seconds: 120,
          },
          cost: {
            estimated_total_cost_usd: 1.23,
            recent: {
              billing_mode: "included",
              configured: true,
              estimated_cost_usd: 0.45,
            },
            remaining: {
              billing_mode: "included",
              configured: true,
              estimated_cost_usd: 0.78,
            },
          },
        },
        checkpoints: {
          pending: null,
        },
        codex_status: {
          account: {
            plan_type: "pro",
          },
          rate_limits: {
            items: [],
          },
          error: "",
        },
      },
      planDraft: {
        steps: [
          { step_id: "ST1", status: "completed" },
          { step_id: "ST2", status: "pending" },
        ],
      },
      form: {
        runtime: {
          generate_word_report: true,
        },
      },
      programSettings: {
        dashboard_visibility: {
          status: true,
          remaining_steps: true,
          estimated_remaining: true,
          estimated_cost: true,
          actual_cost: true,
          runtime_card: false,
          codex_usage_card: false,
          word_report_card: false,
        },
      },
      busy: false,
      modelPresets: [],
      modelCatalog: [],
      activeJob: null,
      onChangeForm: noop,
    },
  );

  assert.doesNotMatch(html, /Estimated Cost/);
  assert.doesNotMatch(html, /Actual Cost/);
});

test("AppSettingsView exposes dashboard visibility controls in the dashboard tab", async () => {
  const html = await renderBundledComponent(
    "app-settings-view-render",
    "./src/components/views/AppSettingsView.jsx",
    "AppSettingsView",
    {
      settings: {
        ui_theme: "dark",
        developer_mode: false,
        model_provider: "openai",
        model: "gpt-5.4",
        model_preset: "",
        model_selection_mode: "slug",
        model_slug_input: "gpt-5.4",
        approval_mode: "never",
        sandbox_mode: "danger-full-access",
        checkpoint_interval_blocks: 1,
        execution_mode: "serial",
        background_concurrency_limit: 3,
        parallel_workers: 2,
        parallel_memory_per_worker_gib: 3,
        codex_path: "codex.cmd",
        allow_push: true,
        require_checkpoint_approval: false,
        dashboard_visibility: {},
      },
      shareSettings: {
        bind_host: "0.0.0.0",
      },
      shareDetail: {
        server: {
          running: false,
        },
      },
      busy: false,
      dirty: true,
      initialSettingsTab: "dashboard",
      onChangeSettings: noop,
      onSaveSettings: noop,
      onGenerateShareLink: noop,
      onCopyShareLink: noop,
      onRevokeShareLink: noop,
      onChangeShareSettings: noop,
    },
  );

  assert.doesNotMatch(html, /Show only the dashboard cards you want to keep visible\./);
  assert.match(html, /Save Program Settings/);
  assert.match(html, /Dashboard/);
  assert.match(html, /Status/);
  assert.match(html, /5h Usage/);
  assert.match(html, /7d Usage/);
  assert.match(html, /Closeout Report/);
  assert.match(html, /Codex Spark/);
  assert.match(html, /Codex Usage/);
  assert.doesNotMatch(html, /Planning Reasoning/);
  assert.doesNotMatch(html, /Custom Model Slug/);
});

test("AppSettingsView remote monitor fixes sharing to 0.0.0.0 and share link only", async () => {
  const html = await renderBundledComponent(
    "app-settings-share-view-render",
    "./src/components/views/AppSettingsView.jsx",
    "AppSettingsView",
    {
      settings: {
        ui_theme: "dark",
        developer_mode: false,
        model_provider: "openai",
        model: "gpt-5.4",
        model_preset: "",
        model_selection_mode: "slug",
        model_slug_input: "gpt-5.4",
        approval_mode: "never",
        sandbox_mode: "danger-full-access",
        checkpoint_interval_blocks: 1,
        execution_mode: "serial",
        parallel_workers: 2,
        parallel_memory_per_worker_gib: 3,
        codex_path: "codex.cmd",
        allow_push: true,
        require_checkpoint_approval: false,
        dashboard_visibility: {},
      },
      shareSettings: {
        bind_host: "0.0.0.0",
      },
      shareDetail: {
        server: {
          running: true,
          base_url: "http://127.0.0.1:43123",
        },
        active_session: {
          share_url: "https://demo.trycloudflare.com/share/view?session=demo&token=secret",
          local_url: "http://127.0.0.1:43123/share/view?session=demo&token=secret",
          expires_at: "2026-03-26T11:00:00+00:00",
        },
      },
      busy: false,
      initialSettingsTab: "share",
      onChangeSettings: noop,
      onGenerateShareLink: noop,
      onCopyShareLink: noop,
      onRevokeShareLink: noop,
      onChangeShareSettings: noop,
    },
  );

  assert.match(html, /0\.0\.0\.0/);
  assert.match(html, /Share Link/);
  assert.doesNotMatch(html, /Local Link/);
  assert.doesNotMatch(html, /Public Share Base URL/);
  assert.doesNotMatch(html, /127\.0\.0\.1/);
});

test("AppSettingsView falls back to the project share session when the workspace active session is missing", async () => {
  const html = await renderBundledComponent(
    "app-settings-share-project-session-render",
    "./src/components/views/AppSettingsView.jsx",
    "AppSettingsView",
    {
      settings: {
        ui_theme: "dark",
        developer_mode: false,
        model_provider: "openai",
        model: "gpt-5.4",
        model_preset: "",
        model_selection_mode: "slug",
        model_slug_input: "gpt-5.4",
        approval_mode: "never",
        sandbox_mode: "danger-full-access",
        checkpoint_interval_blocks: 1,
        execution_mode: "serial",
        parallel_workers: 2,
        parallel_memory_per_worker_gib: 3,
        codex_path: "codex.cmd",
        allow_push: true,
        require_checkpoint_approval: false,
        dashboard_visibility: {},
      },
      shareSettings: {
        bind_host: "0.0.0.0",
      },
      shareDetail: {
        server: {
          running: true,
          base_url: "http://127.0.0.1:43123",
        },
        active_session: null,
        project_active_session: {
          share_url: "https://demo.trycloudflare.com/share/view?session=demo&token=secret",
          local_url: "http://127.0.0.1:43123/share/view?session=demo&token=secret",
          expires_at: "2026-03-26T11:00:00+00:00",
        },
      },
      busy: false,
      initialSettingsTab: "share",
      onChangeSettings: noop,
      onGenerateShareLink: noop,
      onCopyShareLink: noop,
      onRevokeShareLink: noop,
      onChangeShareSettings: noop,
    },
  );

  assert.match(html, /demo\.trycloudflare\.com/);
  assert.doesNotMatch(html, /No active share session\./);
});

test("AppSettingsView keeps share actions enabled while a run is active", async () => {
  const html = await renderBundledComponent(
    "app-settings-share-enabled-render",
    "./src/components/views/AppSettingsView.jsx",
    "AppSettingsView",
    {
      settings: {
        ui_theme: "dark",
        developer_mode: false,
        model_provider: "openai",
        model: "gpt-5.4",
        model_preset: "",
        model_selection_mode: "slug",
        model_slug_input: "gpt-5.4",
        approval_mode: "never",
        sandbox_mode: "danger-full-access",
        checkpoint_interval_blocks: 1,
        execution_mode: "serial",
        parallel_workers: 2,
        parallel_memory_per_worker_gib: 3,
        codex_path: "codex.cmd",
        allow_push: true,
        require_checkpoint_approval: false,
        dashboard_visibility: {},
      },
      shareSettings: {
        bind_host: "0.0.0.0",
      },
      shareDetail: {
        server: {
          running: true,
        },
        active_session: {
          share_url: "https://demo.trycloudflare.com/share/view?session=demo&token=secret",
          expires_at: "2026-03-26T11:00:00+00:00",
        },
      },
      busy: true,
      shareBusy: false,
      initialSettingsTab: "share",
      onChangeSettings: noop,
      onGenerateShareLink: noop,
      onCopyShareLink: noop,
      onRevokeShareLink: noop,
      onChangeShareSettings: noop,
    },
  );

  assert.match(html, /Generate Share Link/);
  assert.match(html, /toolbar-button toolbar-button--accent[\s\S]*title="Copy Link"/);
  assert.match(html, /Revoke Link/);
});

test("ConfigEditorView no longer renders the advanced settings section", async () => {
  const html = await renderBundledComponent(
    "config-editor-view-render",
    "./src/components/views/ConfigEditorView.jsx",
    "ConfigEditorView",
    {
      form: {
        project_dir: "C:/demo",
        display_name: "Demo",
        branch: "main",
        github_mode: "existing",
        origin_url: "",
        runtime: {
          model_provider: "openai",
          model: "auto",
          model_preset: "auto",
          model_slug_input: "auto",
          effort: "medium",
          workflow_mode: "standard",
          execution_mode: "serial",
          parallel_workers: 2,
          parallel_memory_per_worker_gib: 3,
          ml_max_cycles: 3,
          max_blocks: 5,
        },
      },
      modelPresets: [],
      modelCatalog: [
        {
          model: "auto",
          display_name: "Auto",
          hidden: false,
          default_reasoning_effort: "medium",
          supported_reasoning_efforts: ["low", "medium", "high", "xhigh"],
        },
      ],
      busy: false,
      onChangeForm: noop,
      onSaveProject: noop,
      onChooseDirectory: noop,
      onArchiveProject: noop,
      onDeleteProject: noop,
    },
  );

  assert.doesNotMatch(html, /Advanced Settings/);
  assert.doesNotMatch(html, /Custom Model Slug/);
  assert.match(html, />Save Configuration<\/button>/);
  assert.match(html, /Planning Reasoning/);
  assert.match(html, /Memory \/ Worker \(GiB\)/);
  assert.doesNotMatch(html, /Extra Prompt/);
  assert.match(html, />Archive Project<\/button>/);
  assert.match(html, />Delete Project<\/button>/);
});

test("ConfigEditorView keeps checkpoint controls editable during an active run", async () => {
  const html = await renderBundledComponent(
    "config-editor-live-runtime-render",
    "./src/components/views/ConfigEditorView.jsx",
    "ConfigEditorView",
    {
      form: {
        project_dir: "C:/demo",
        display_name: "Demo",
        branch: "main",
        github_mode: "existing",
        origin_url: "",
        runtime: {
          model_provider: "openai",
          model: "gpt-5.4",
          model_preset: "",
          model_slug_input: "gpt-5.4",
          effort: "medium",
          workflow_mode: "standard",
          execution_mode: "parallel",
          parallel_worker_mode: "auto",
          parallel_workers: 0,
          parallel_memory_per_worker_gib: 3,
          checkpoint_interval_blocks: 2,
          require_checkpoint_approval: true,
          generate_word_report: true,
          ml_max_cycles: 3,
          max_blocks: 5,
        },
      },
      modelPresets: [],
      modelCatalog: [
        {
          model: "gpt-5.4",
          display_name: "GPT-5.4",
          hidden: false,
          default_reasoning_effort: "medium",
          supported_reasoning_efforts: ["low", "medium", "high", "xhigh"],
        },
      ],
      busy: true,
      activeJob: {
        status: "running",
        command: "run-plan",
      },
      onChangeForm: noop,
      onSaveProject: noop,
      onChooseDirectory: noop,
      onArchiveProject: noop,
      onDeleteProject: noop,
    },
  );

  assert.match(html, /Save Configuration/);
  const saveButtonMatch = html.match(/<button[^>]*>Save Configuration<\/button>/);
  assert.ok(saveButtonMatch, "Save Configuration button should exist");
  assert.doesNotMatch(saveButtonMatch[0], /disabled=""/);
  assert.match(html, /Safe runtime settings like checkpoints and report output can still be saved while a run is active\./);
  assert.match(html, /Checkpoint Interval/);
  assert.match(html, /Require checkpoint approval/);
  assert.doesNotMatch(html, /Word Report Creation/);
});

test("DetailsPane shows report documents and checkpoint deadlines in the inspector", async () => {
  const html = await renderBundledComponent(
    "details-pane-documents-render",
    "./src/components/layout/DetailsPane.jsx",
    "DetailsPane",
    {
      detail: {
        project: {
          current_status: "running:parallel",
          display_name: "Demo",
          slug: "demo",
          branch: "main",
          repo_path: "C:/demo",
          current_safe_revision: "abc123",
        },
        runtime: {
          model: "gpt-5.4",
          effort: "medium",
          generate_word_report: true,
        },
        checkpoints: {
          pending: {
            checkpoint_id: "CP1",
            title: "Prepare release",
            target_block: 1,
            status: "awaiting_review",
            deadline_at: "2026-04-05 18:00",
          },
        },
        reports: {
          closeout_report_text: "# Closeout Report",
          word_report_path: "C:/demo/reports/CLOSEOUT_REPORT.docx",
          powerpoint_report_path: "",
          powerpoint_report_target_path: "C:/demo/reports/CLOSEOUT_REPORT.pptx",
          ml_experiment_report_text: "",
        },
        files: {
          closeout_report_file: "C:/demo/docs/CLOSEOUT_REPORT.md",
          word_report_file: "C:/demo/reports/CLOSEOUT_REPORT.docx",
          powerpoint_report_file: "C:/demo/reports/CLOSEOUT_REPORT.pptx",
          ml_experiment_report_file: "C:/demo/docs/ML_EXPERIMENT_REPORT.md",
        },
      },
      planDraft: {
        steps: [
          {
            step_id: "ST1",
            title: "Prepare release",
            display_description: "Prepare release checkpoint",
            success_criteria: "Release notes updated",
            reasoning_effort: "medium",
            deadline_at: "2026-04-05 18:00",
            status: "pending",
          },
        ],
      },
      selectedStepId: "ST1",
      modelPresets: [],
      onHide: noop,
    },
  );

  assert.match(html, /Documents/);
  assert.match(html, /PowerPoint Report/);
  assert.match(html, /C:\/demo\/reports\/CLOSEOUT_REPORT\.pptx/);
  assert.match(html, /Deadline:/);
  assert.match(html, /2026-04-05 18:00/);
});

test("ConfigEditorView keeps a selected model visible even when the catalog omits it", async () => {
  const html = await renderBundledComponent(
    "config-editor-selected-model-render",
    "./src/components/views/ConfigEditorView.jsx",
    "ConfigEditorView",
    {
      form: {
        project_dir: "C:/demo",
        display_name: "Demo",
        branch: "main",
        github_mode: "existing",
        origin_url: "",
        runtime: {
          model_provider: "openai",
          model: "gpt-5.4",
          model_preset: "",
          model_slug_input: "gpt-5.4",
          effort: "medium",
          workflow_mode: "standard",
          execution_mode: "serial",
          parallel_workers: 2,
          parallel_memory_per_worker_gib: 3,
          ml_max_cycles: 3,
          max_blocks: 5,
        },
      },
      modelPresets: [],
      modelCatalog: [
        {
          model: "gpt-5.3-codex-spark",
          display_name: "GPT-5.3-Codex-Spark",
          hidden: false,
          default_reasoning_effort: "high",
          supported_reasoning_efforts: ["low", "medium", "high", "xhigh"],
        },
      ],
      busy: false,
      onChangeForm: noop,
      onChooseDirectory: noop,
      onArchiveProject: noop,
      onDeleteProject: noop,
    },
  );

  assert.match(html, /gpt-5\.4/);
  assert.match(html, /GPT-5\.3-Codex-Spark/);
});

test("ConfigEditorView renders provider-scoped catalog models for Gemini CLI projects", async () => {
  const html = await renderBundledComponent(
    "config-editor-gemini-model-render",
    "./src/components/views/ConfigEditorView.jsx",
    "ConfigEditorView",
    {
      form: {
        project_dir: "C:/demo",
        display_name: "Demo",
        branch: "main",
        github_mode: "existing",
        origin_url: "",
        runtime: {
          model_provider: "gemini",
          model: "gemini-2.5-pro",
          model_preset: "",
          model_slug_input: "gemini-2.5-pro",
          effort: "medium",
          workflow_mode: "standard",
          execution_mode: "parallel",
          parallel_worker_mode: "auto",
          parallel_workers: 0,
          parallel_memory_per_worker_gib: 3,
          ml_max_cycles: 3,
          max_blocks: 5,
        },
      },
      modelPresets: [],
      modelCatalog: [
        {
          model: "gpt-5.4",
          display_name: "GPT-5.4",
          hidden: false,
          provider: "openai",
          default_reasoning_effort: "medium",
          supported_reasoning_efforts: ["low", "medium", "high", "xhigh"],
        },
        {
          model: "gemini-3-flash-preview",
          display_name: "Gemini 3 Flash Preview",
          hidden: false,
          provider: "gemini",
          default_reasoning_effort: "medium",
          supported_reasoning_efforts: ["medium"],
        },
        {
          model: "gemini-2.5-pro",
          display_name: "Gemini 2.5 Pro",
          hidden: false,
          provider: "gemini",
          default_reasoning_effort: "medium",
          supported_reasoning_efforts: ["medium"],
        },
      ],
      busy: false,
      onChangeForm: noop,
      onChooseDirectory: noop,
      onArchiveProject: noop,
      onDeleteProject: noop,
    },
  );

  assert.match(html, /Gemini 3 Flash Preview/);
  assert.match(html, /Gemini 2\.5 Pro/);
  assert.doesNotMatch(html, /GPT-5\.4/);
});

test("ConfigEditorView renders the current ensemble model selectors in project settings", async () => {
  const html = await renderBundledComponent(
    "config-editor-ensemble-model-render",
    "./src/components/views/ConfigEditorView.jsx",
    "ConfigEditorView",
    {
      form: {
        project_dir: "C:/demo",
        display_name: "Demo",
        branch: "main",
        github_mode: "existing",
        origin_url: "",
        runtime: {
          model_provider: "ensemble",
          model: "gpt-5.4-mini",
          model_preset: "",
          model_slug_input: "gpt-5.4-mini",
          ensemble_openai_model: "gpt-5.4-mini",
          ensemble_gemini_model: "gemini-2.5-pro",
          ensemble_claude_model: "claude-3.7-sonnet",
          effort: "medium",
          planning_effort: "medium",
          workflow_mode: "standard",
          execution_mode: "parallel",
          parallel_worker_mode: "auto",
          parallel_workers: 0,
          parallel_memory_per_worker_gib: 3,
          ml_max_cycles: 3,
          max_blocks: 5,
        },
      },
      modelPresets: [],
      modelCatalog: [
        {
          model: "gpt-5.4-mini",
          display_name: "GPT-5.4 Mini",
          hidden: false,
          provider: "openai",
          default_reasoning_effort: "medium",
          supported_reasoning_efforts: ["low", "medium", "high", "xhigh"],
        },
        {
          model: "gemini-2.5-pro",
          display_name: "Gemini 2.5 Pro",
          hidden: false,
          provider: "gemini",
          default_reasoning_effort: "medium",
          supported_reasoning_efforts: ["medium"],
        },
        {
          model: "claude-3.7-sonnet",
          display_name: "Claude 3.7 Sonnet",
          hidden: false,
          provider: "claude",
          default_reasoning_effort: "medium",
          supported_reasoning_efforts: ["low", "medium", "high", "xhigh"],
        },
      ],
      busy: false,
      onChangeForm: noop,
      onChangeProgramSettings: noop,
      onChooseDirectory: noop,
      onArchiveProject: noop,
      onDeleteProject: noop,
    },
  );

  assert.match(html, /Codex Model/);
  assert.match(html, /GPT Model/);
  assert.match(html, /Claude Model/);
  assert.match(html, /GPT-5\.4 Mini/);
  assert.match(html, /Claude 3\.7 Sonnet/);
  assert.doesNotMatch(html, /Gemini Model/);
});

test("AppSettingsView keeps direct model slug editing for OpenRouter only", async () => {
  const html = await renderBundledComponent(
    "app-settings-openrouter-model-render",
    "./src/components/views/AppSettingsView.jsx",
    "AppSettingsView",
    {
      settings: {
        model_provider: "openrouter",
        provider_api_key_env: "OPENROUTER_API_KEY",
        provider_base_url: "https://openrouter.ai/api/v1",
        model: "openai/gpt-5.4",
        model_slug_input: "openai/gpt-5.4",
        approval_mode: "never",
        sandbox_mode: "danger-full-access",
        checkpoint_interval_blocks: 1,
        workflow_mode: "standard",
        planning_effort: "medium",
        ml_max_cycles: 3,
        parallel_worker_mode: "manual",
        parallel_workers: 4,
        parallel_memory_per_worker_gib: 3,
        background_concurrency_limit: 2,
        dashboard_visibility: {},
        codex_path: "codex.cmd",
      },
      shareSettings: {},
      shareDetail: {},
      busy: false,
      shareBusy: false,
      initialSettingsTab: "execution",
      onChangeSettings: noop,
      onGenerateShareLink: noop,
      onCopyShareLink: noop,
      onRevokeShareLink: noop,
      onChangeShareSettings: noop,
    },
  );

  assert.match(html, /Custom Model Slug/);
});

test("AppSettingsView surfaces provider availability warnings in the execution tab", async () => {
  const html = await renderBundledComponent(
    "app-settings-provider-availability-render",
    "./src/components/views/AppSettingsView.jsx",
    "AppSettingsView",
    {
      settings: {
        model_provider: "claude",
        provider_api_key_env: "ANTHROPIC_API_KEY",
        provider_base_url: "",
        model: "claude-3.7-sonnet",
        model_slug_input: "claude-3.7-sonnet",
        approval_mode: "never",
        sandbox_mode: "danger-full-access",
        checkpoint_interval_blocks: 1,
        workflow_mode: "standard",
        planning_effort: "medium",
        ml_max_cycles: 3,
        parallel_worker_mode: "manual",
        parallel_workers: 4,
        parallel_memory_per_worker_gib: 3,
        background_concurrency_limit: 2,
        dashboard_visibility: {},
        codex_path: "codex.cmd",
      },
      codexStatus: {
        provider_statuses: {
          ensemble: { available: false, reason: "The ensemble requires all three installed backends: missing claude." },
          openai: { available: true, reason: "Codex CLI is available." },
          claude: { available: false, reason: "Claude Code is not installed." },
          gemini: { available: true, reason: "Gemini CLI is available." },
        },
      },
      shareSettings: {},
      shareDetail: {},
      busy: false,
      shareBusy: false,
      initialSettingsTab: "execution",
      onChangeSettings: noop,
      onGenerateShareLink: noop,
      onCopyShareLink: noop,
      onRevokeShareLink: noop,
      onChangeShareSettings: noop,
    },
  );

  assert.match(html, /not installed/);
  assert.match(html, /Claude Code is not installed\./);
  assert.match(html, /provider-sub-card active/);
  assert.match(html, /Gemini/);
});

test("ReportsView shows the saved Word report path next to the closeout report", async () => {
  const html = await renderBundledComponent(
    "reports-view-word-path-render",
    "./src/components/views/ReportsView.jsx",
    "ReportsView",
    {
      reports: {
        closeout_report_text: "# Closeout Report\n\nDone.",
        ml_experiment_report_text: "No ML experiment report yet.",
        attempt_history_text: "Attempt 1",
        word_report_enabled: true,
        word_report_path: "C:/workspace/reports/CLOSEOUT_REPORT.docx",
      },
    },
  );

  assert.match(html, /Closeout Report/);
  assert.match(html, /Word report saved at C:\/workspace\/reports\/CLOSEOUT_REPORT\.docx/);
  assert.match(html, /Attempt 1/);
});

test("HistoryView exposes a delete action for archived runs", async () => {
  const html = await renderBundledComponent(
    "history-view-render",
    "./src/components/views/HistoryView.jsx",
    "HistoryView",
    {
      detail: {
        project: {
          archive_id: "hist-1",
          display_name: "Archived Demo",
          current_status: "closed_out",
          archived_at: "2026-03-27T00:00:00+00:00",
        },
        history: {
          flow_svg_text: "<svg></svg>",
          blocks: [],
          ui_events: [],
        },
        plan: {
          project_prompt: "Recover the archived run.",
        },
        summary: "Archived detail summary",
      },
      busy: false,
      onDeleteHistoryEntry: noop,
    },
  );

  assert.match(html, />Delete Archived Run<\/button>/);
});

test("IdeToolbar labels the top settings action as Program Settings", async () => {
  const html = await renderBundledComponent(
    "ide-toolbar-program-settings-render",
    "./src/components/layout/IdeToolbar.jsx",
    "IdeToolbar",
    {
      projects: [],
      selectedProjectId: "",
      onSelectProject: noop,
      onNewProject: noop,
      projectDetail: {
        project: {
          current_status: "idle",
        },
      },
      planDraft: {
        steps: [],
      },
      pendingCheckpoint: null,
      busy: false,
      activeJob: null,
      activeCenterTab: "app-settings",
      projectPath: "",
      githubUrl: "",
      shareUrl: "",
      shareBusy: false,
      onRefresh: noop,
      onOpenSettings: noop,
      onGeneratePlan: noop,
      onRunPlan: noop,
      onApproveCheckpoint: noop,
      onSmartShareLink: noop,
      onOpenFolder: noop,
      onOpenVsCode: noop,
      onOpenGithub: noop,
    },
  );

  assert.match(html, /Program Settings/);
});

test("IdeToolbar keeps the remote link button enabled without a selected project", async () => {
  const html = await renderBundledComponent(
    "ide-toolbar-remote-link-without-project-render",
    "./src/components/layout/IdeToolbar.jsx",
    "IdeToolbar",
    {
      projects: [],
      selectedProjectId: "",
      onSelectProject: noop,
      onNewProject: noop,
      projectDetail: null,
      planDraft: {
        steps: [],
      },
      pendingCheckpoint: null,
      busy: false,
      activeJob: null,
      activeCenterTab: "run",
      projectPath: "",
      githubUrl: "",
      shareUrl: "",
      shareBusy: false,
      onRefresh: noop,
      onOpenSettings: noop,
      onGeneratePlan: noop,
      onRunPlan: noop,
      onApproveCheckpoint: noop,
      onSmartShareLink: noop,
      onOpenFolder: noop,
      onOpenVsCode: noop,
      onOpenGithub: noop,
    },
  );

  const remoteButton = html.match(/<button[^>]*aria-label="Remote Control"[^>]*>/)?.[0] || "";
  assert.ok(remoteButton, "expected remote link button to render");
  assert.doesNotMatch(remoteButton, /\sdisabled(?:=|>|\s)/);
});
