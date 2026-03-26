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
      },
    },
    form: {
      runtime: {
        execution_mode: "serial",
      },
    },
    shareSettings: {
      bind_host: "127.0.0.1",
      public_base_url: "",
    },
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
    onDeleteProject: noop,
    onGenerateShareLink: noop,
    onCopyShareLink: noop,
    onRevokeShareLink: noop,
    onChangeShareSettings: noop,
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

test("CenterWorkspace renders the serial flow view for serial plans", async () => {
  const html = await renderBundledComponent(
    "center-workspace-render",
    "./src/components/layout/CenterWorkspace.jsx",
    "CenterWorkspace",
    baseWorkspaceProps(),
  );

  assert.match(html, /Execution Flow/);
  assert.match(html, /Flow Chart/);
  assert.match(html, /Execution Mode/);
  assert.match(html, /Serial/);
  assert.doesNotMatch(html, /Execution Tree/);
});

test("CenterWorkspace renders the parallel execution tree for parallel plans", async () => {
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

  assert.match(html, /Execution Tree/);
  assert.match(html, /Ready Nodes/);
  assert.match(html, /Depends On/);
  assert.match(html, /Owned Paths/);
  assert.doesNotMatch(html, /Flow Chart/);
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
  });

  assert.match(html, /Run Remaining Steps/);
  assert.match(html, /Completed 1\/3 steps, ready: ST2, ST3/);
  assert.match(html, /Program Settings/);
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
  });

  assert.match(html, /Debugging/);
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
        "2026-03-26T09:01:00Z | step-started [ST2] | Running ST2: Build the screen",
      ],
      plan: {
        execution_mode: "parallel",
        closeout_status: "not_started",
        steps: [
          { step_id: "ST1", title: "Plan", status: "completed" },
          { step_id: "ST2", title: "Build", status: "running", depends_on: ["ST1"], owned_paths: ["desktop/src"] },
          { step_id: "ST3", title: "Backend", status: "pending", depends_on: ["ST1"], owned_paths: ["src/jakal_flow"] },
        ],
      },
      stats: {
        total_steps: 3,
        completed_steps: 1,
        failed_steps: 0,
        running_steps: 1,
        remaining_steps: 2,
      },
    },
    planDraft: {
      execution_mode: "parallel",
      closeout_status: "not_started",
      steps: [
        { step_id: "ST1", title: "Plan", status: "completed" },
        { step_id: "ST2", title: "Build", status: "running", depends_on: ["ST1"], owned_paths: ["desktop/src"] },
        { step_id: "ST3", title: "Backend", status: "pending", depends_on: ["ST1"], owned_paths: ["src/jakal_flow"] },
      ],
    },
    activeJob: {
      status: "running",
      command: "run-plan",
    },
  });

  assert.match(html, /Live Run/);
  assert.match(html, /Working on ST2 - Build/);
  assert.match(html, /Completed 1\/3 steps, ready: ST2, ST3/);
  assert.match(html, /Running ST2: Build the screen/);
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
    onDeleteProject: noop,
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
      onDeleteProject: noop,
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
  assert.doesNotMatch(html, /Status/);
  assert.doesNotMatch(html, /Runtime/);
  assert.doesNotMatch(html, /Closeout Report/);
});

test("AppSettingsView exposes dashboard visibility controls", async () => {
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
        parallel_workers: 2,
        codex_path: "codex.cmd",
        allow_push: true,
        require_checkpoint_approval: false,
        dashboard_visibility: {},
      },
      shareSettings: {
        bind_host: "127.0.0.1",
        public_base_url: "",
      },
      shareDetail: {
        server: {
          running: false,
        },
      },
      busy: false,
      onChangeSettings: noop,
      onGenerateShareLink: noop,
      onCopyShareLink: noop,
      onRevokeShareLink: noop,
      onChangeShareSettings: noop,
    },
  );

  assert.match(html, /Show only the dashboard cards you want to keep visible\./);
  assert.match(html, /Custom Model Slug/);
  assert.match(html, /Rate Limits/);
  assert.match(html, /Codex Usage/);
  assert.doesNotMatch(html, /Billing Mode/);
  assert.doesNotMatch(html, /Input \$ \/ 1M/);
});
