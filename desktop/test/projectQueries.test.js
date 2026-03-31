import assert from "node:assert/strict";
import test from "node:test";

import {
  fetchProjectChat,
  fetchProjectCheckpoints,
  fetchProjectDetail,
  fetchProjectHistory,
  fetchProjectReports,
  fetchProjectWorkspace,
  loadInitialDesktopState,
  loadWorkspaceShareDetail,
  refreshVisibleProjectState,
} from "../src/controller/projectQueries.js";

test("refreshVisibleProjectState loads listing and selected project detail with one bridge request", async () => {
  const calls = [];
  const bridgeRequest = async (command, payload, workspaceRoot) => {
    calls.push({ command, payload, workspaceRoot });
    if (command === "load-visible-project-state") {
      await new Promise((resolve) => setTimeout(resolve, 40));
      return {
        listing: { projects: [{ repo_id: "demo" }] },
        detail: { project: { repo_id: "demo" }, detail_level: "core" },
      };
    }
    throw new Error(`Unexpected command: ${command}`);
  };

  const startedAt = Date.now();
  const result = await refreshVisibleProjectState(bridgeRequest, "/workspace", "demo", { detailLevel: "core" });
  const elapsedMs = Date.now() - startedAt;

  assert.deepEqual(result, {
    listing: { projects: [{ repo_id: "demo" }] },
    detail: { project: { repo_id: "demo" }, detail_level: "core" },
  });
  assert.deepEqual(calls, [
    {
      command: "load-visible-project-state",
      payload: {
        repo_id: "demo",
        refresh_codex_status: false,
        detail_level: "core",
        include_listing: true,
        bypass_detail_cache: false,
        bypass_listing_cache: false,
      },
      workspaceRoot: "/workspace",
    },
  ]);
  assert.ok(elapsedMs < 70, `expected combined refresh to finish quickly, took ${elapsedMs}ms`);
});

test("refreshVisibleProjectState skips detail loading when no project is selected", async () => {
  const calls = [];
  const bridgeRequest = async (command, payload, workspaceRoot) => {
    calls.push({ command, payload, workspaceRoot });
    return { listing: { projects: [] }, detail: null };
  };

  const result = await refreshVisibleProjectState(bridgeRequest, "/workspace", "", { detailLevel: "core" });

  assert.deepEqual(result, {
    listing: { projects: [] },
    detail: null,
  });
  assert.deepEqual(calls, [
    {
      command: "load-visible-project-state",
      payload: {
        refresh_codex_status: false,
        detail_level: "core",
        include_listing: true,
        bypass_detail_cache: false,
        bypass_listing_cache: false,
      },
      workspaceRoot: "/workspace",
    },
  ]);
});

test("refreshVisibleProjectState can skip listing when only selected detail needs a live refresh", async () => {
  const calls = [];
  const bridgeRequest = async (command, payload, workspaceRoot) => {
    calls.push({ command, payload, workspaceRoot });
    if (command === "load-visible-project-state") {
      return { detail: { project: { repo_id: "demo" }, detail_level: "full" } };
    }
    throw new Error(`Unexpected command: ${command}`);
  };

  const result = await refreshVisibleProjectState(bridgeRequest, "/workspace", "demo", {
    detailLevel: "full",
    refreshListing: false,
  });

  assert.deepEqual(result, {
    listing: null,
    detail: { project: { repo_id: "demo" }, detail_level: "full" },
  });
  assert.deepEqual(calls, [
    {
      command: "load-visible-project-state",
      payload: {
        repo_id: "demo",
        refresh_codex_status: false,
        detail_level: "full",
        include_listing: false,
        bypass_detail_cache: false,
        bypass_listing_cache: false,
      },
      workspaceRoot: "/workspace",
    },
  ]);
});

test("refreshVisibleProjectState can bypass cached detail when manually refreshing an open project", async () => {
  const calls = [];
  const bridgeRequest = async (command, payload, workspaceRoot) => {
    calls.push({ command, payload, workspaceRoot });
    if (command === "load-visible-project-state") {
      return {
        listing: { projects: [{ repo_id: "demo" }] },
        detail: { project: { repo_id: "demo" }, detail_level: "core" },
      };
    }
    throw new Error(`Unexpected command: ${command}`);
  };

  const result = await refreshVisibleProjectState(bridgeRequest, "/workspace", "demo", {
    detailLevel: "core",
    bypassDetailCache: true,
  });

  assert.deepEqual(result, {
    listing: { projects: [{ repo_id: "demo" }] },
    detail: { project: { repo_id: "demo" }, detail_level: "core" },
  });
  assert.deepEqual(calls, [
    {
      command: "load-visible-project-state",
      payload: {
        repo_id: "demo",
        refresh_codex_status: false,
        detail_level: "core",
        include_listing: true,
        bypass_detail_cache: true,
        bypass_listing_cache: false,
      },
      workspaceRoot: "/workspace",
    },
  ]);
});

test("refreshVisibleProjectState can bypass cached listing and cached detail together", async () => {
  const calls = [];
  const bridgeRequest = async (command, payload, workspaceRoot) => {
    calls.push({ command, payload, workspaceRoot });
    if (command === "load-visible-project-state") {
      return {
        listing: { projects: [{ repo_id: "demo" }] },
        detail: { project: { repo_id: "demo" }, detail_level: "core" },
      };
    }
    throw new Error(`Unexpected command: ${command}`);
  };

  const result = await refreshVisibleProjectState(bridgeRequest, "/workspace", "demo", {
    detailLevel: "core",
    bypassDetailCache: true,
    bypassListingCache: true,
  });

  assert.deepEqual(result, {
    listing: { projects: [{ repo_id: "demo" }] },
    detail: { project: { repo_id: "demo" }, detail_level: "core" },
  });
  assert.deepEqual(calls, [
    {
      command: "load-visible-project-state",
      payload: {
        repo_id: "demo",
        refresh_codex_status: false,
        detail_level: "core",
        include_listing: true,
        bypass_detail_cache: true,
        bypass_listing_cache: true,
      },
      workspaceRoot: "/workspace",
    },
  ]);
});

test("fetchProjectDetail forwards bypassDetailCache to the bridge payload", async () => {
  const calls = [];
  const bridgeRequest = async (command, payload, workspaceRoot) => {
    calls.push({ command, payload, workspaceRoot });
    if (command === "load-project") {
      return { project: { repo_id: "demo" }, detail_level: "core" };
    }
    throw new Error(`Unexpected command: ${command}`);
  };

  const result = await fetchProjectDetail(bridgeRequest, "demo", "/workspace", {
    detailLevel: "core",
    refreshCodexStatus: false,
    bypassDetailCache: true,
  });

  assert.deepEqual(result, { project: { repo_id: "demo" }, detail_level: "core" });
  assert.deepEqual(calls, [
    {
      command: "load-project",
      payload: {
        repo_id: "demo",
        refresh_codex_status: false,
        detail_level: "core",
        bypass_detail_cache: true,
      },
      workspaceRoot: "/workspace",
    },
  ]);
});

test("loadInitialDesktopState overlaps bootstrap and job snapshot loading", async () => {
  const bridgeRequest = async (command, _payload, workspaceRoot) => {
    if (command === "bootstrap") {
      await new Promise((resolve) => setTimeout(resolve, 40));
      return { workspace_root: "/workspace" };
    }
    if (command === "list-projects") {
      assert.equal(workspaceRoot, "/workspace");
      return { projects: [] };
    }
    throw new Error(`Unexpected command: ${command}`);
  };

  const originalListBridgeJobs = globalThis.__JAKAL_FLOW_TEST_LIST_BRIDGE_JOBS__;
  globalThis.__JAKAL_FLOW_TEST_LIST_BRIDGE_JOBS__ = async () => {
    await new Promise((resolve) => setTimeout(resolve, 40));
    return [];
  };

  const startedAt = Date.now();
  try {
    const result = await loadInitialDesktopState(bridgeRequest);
    const elapsedMs = Date.now() - startedAt;

    assert.deepEqual(result, {
      bootstrap: { workspace_root: "/workspace" },
      listing: { projects: [] },
      jobSnapshot: {
        jobs: [],
        runningJob: null,
        activeJob: null,
        activeJobId: "",
      },
    });
    assert.ok(elapsedMs < 70, `expected bootstrap and jobs to overlap, took ${elapsedMs}ms`);
  } finally {
    globalThis.__JAKAL_FLOW_TEST_LIST_BRIDGE_JOBS__ = originalListBridgeJobs;
  }
});

test("loadInitialDesktopState keeps queued jobs as the active snapshot when nothing is running", async () => {
  const bridgeRequest = async (command, _payload, workspaceRoot) => {
    if (command === "bootstrap") {
      return { workspace_root: "/workspace" };
    }
    if (command === "list-projects") {
      assert.equal(workspaceRoot, "/workspace");
      return { projects: [] };
    }
    throw new Error(`Unexpected command: ${command}`);
  };

  const originalListBridgeJobs = globalThis.__JAKAL_FLOW_TEST_LIST_BRIDGE_JOBS__;
  globalThis.__JAKAL_FLOW_TEST_LIST_BRIDGE_JOBS__ = async () => [
    { id: "job-queued", status: "queued", command: "run-plan" },
  ];

  try {
    const result = await loadInitialDesktopState(bridgeRequest, "job-queued");

    assert.equal(result.jobSnapshot.activeJob?.id, "job-queued");
    assert.equal(result.jobSnapshot.activeJobId, "job-queued");
    assert.equal(result.jobSnapshot.runningJob, null);
  } finally {
    globalThis.__JAKAL_FLOW_TEST_LIST_BRIDGE_JOBS__ = originalListBridgeJobs;
  }
});

test("project supplement fetches wrap partial bridge payloads for detail merging", async () => {
  const calls = [];
  const bridgeRequest = async (command, payload, workspaceRoot) => {
    calls.push({ command, payload, workspaceRoot });
    if (command === "load-project-chat") {
      return {
        chat: {
          sessions: [{ session_id: "chat-1" }],
          active_session_id: "chat-1",
          active_session: { session_id: "chat-1" },
          messages: [{ message_id: "msg-1", role: "assistant", text: "hello" }],
          summary_text: "summary",
          summary_file: "/workspace/chat.summary.txt",
          transcript_file: "/workspace/chat.transcript.txt",
          draft_session: false,
        },
      };
    }
    if (command === "load-project-reports") {
      return { closeout_report_text: "done" };
    }
    if (command === "load-project-workspace") {
      return { workspace_tree: [{ label: "Repository" }] };
    }
    if (command === "load-project-checkpoints") {
      return { items: [], pending: null, timeline_markdown: "" };
    }
    if (command === "load-project-history") {
      return { ui_events: [], blocks: [], passes: [], test_runs: [], flow_svg_text: "" };
    }
    throw new Error(`Unexpected command: ${command}`);
  };

  assert.deepEqual(await fetchProjectChat(bridgeRequest, "demo", "/workspace", { sessionId: "chat-1" }), {
    chat: {
      sessions: [{ session_id: "chat-1" }],
      active_session_id: "chat-1",
      active_session: { session_id: "chat-1" },
      messages: [{ message_id: "msg-1", role: "assistant", text: "hello" }],
      summary_text: "summary",
      summary_file: "/workspace/chat.summary.txt",
      transcript_file: "/workspace/chat.transcript.txt",
      draft_session: false,
    },
    loaded_sections: { chat: true },
  });
  assert.deepEqual(await fetchProjectReports(bridgeRequest, "demo", "/workspace"), {
    reports: { closeout_report_text: "done" },
    loaded_sections: { reports: true },
  });
  assert.deepEqual(await fetchProjectWorkspace(bridgeRequest, "demo", "/workspace"), {
    workspace_tree: [{ label: "Repository" }],
    loaded_sections: { workspace: true },
  });
  assert.deepEqual(await fetchProjectCheckpoints(bridgeRequest, "demo", "/workspace"), {
    checkpoints: { items: [], pending: null, timeline_markdown: "" },
    loaded_sections: { checkpoints: true },
  });
  assert.deepEqual(await fetchProjectHistory(bridgeRequest, "demo", "/workspace"), {
    history: { ui_events: [], blocks: [], passes: [], test_runs: [], flow_svg_text: "" },
    loaded_sections: { history: true },
  });
  assert.deepEqual(calls, [
    {
      command: "load-project-chat",
      payload: { repo_id: "demo", session_id: "chat-1" },
      workspaceRoot: "/workspace",
    },
    {
      command: "load-project-reports",
      payload: { repo_id: "demo" },
      workspaceRoot: "/workspace",
    },
    {
      command: "load-project-workspace",
      payload: { repo_id: "demo" },
      workspaceRoot: "/workspace",
    },
    {
      command: "load-project-checkpoints",
      payload: { repo_id: "demo" },
      workspaceRoot: "/workspace",
    },
    {
      command: "load-project-history",
      payload: { repo_id: "demo" },
      workspaceRoot: "/workspace",
    },
  ]);
});

test("loadWorkspaceShareDetail fetches workspace share only on demand", async () => {
  const calls = [];
  const bridgeRequest = async (command, payload, workspaceRoot) => {
    calls.push({ command, payload, workspaceRoot });
    return { share: { active_session: null } };
  };

  const result = await loadWorkspaceShareDetail(bridgeRequest, "/workspace");

  assert.deepEqual(result, { share: { active_session: null } });
  assert.deepEqual(calls, [
    {
      command: "load-workspace-share",
      payload: {},
      workspaceRoot: "/workspace",
    },
  ]);
});
