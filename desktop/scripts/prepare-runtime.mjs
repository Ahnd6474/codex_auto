import { spawnSync } from "node:child_process";
import { open, readFile, rm } from "node:fs/promises";
import { delimiter } from "node:path";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(scriptDir, "..", "..");
const srcRoot = join(repoRoot, "src");
const targetDir = join(repoRoot, "rt");
const lockFile = join(repoRoot, ".prepare-runtime.lock");
const lockTimeoutMs = 5 * 60 * 1000;
const lockPollIntervalMs = 1000;
const runtimeProfile = (() => {
  const profileIndex = process.argv.findIndex((value) => value === "--profile");
  if (profileIndex >= 0) {
    return String(process.argv[profileIndex + 1] || "").trim().toLowerCase() || "full";
  }
  const positional = process.argv[2];
  return String(positional || "").trim().toLowerCase() || "full";
})();

const env = {
  ...process.env,
  PYTHONPATH: process.env.PYTHONPATH ? `${srcRoot}${delimiter}${process.env.PYTHONPATH}` : srcRoot,
};

function sleep(ms) {
  return new Promise((resolvePromise) => {
    setTimeout(resolvePromise, ms);
  });
}

function pidIsRunning(pid) {
  const normalizedPid = Number.parseInt(String(pid || ""), 10);
  if (!Number.isInteger(normalizedPid) || normalizedPid <= 0) {
    return false;
  }
  try {
    process.kill(normalizedPid, 0);
    return true;
  } catch (error) {
    return error?.code === "EPERM";
  }
}

async function readLockPayload() {
  try {
    const raw = await readFile(lockFile, "utf-8");
    return JSON.parse(String(raw || "").trim());
  } catch {
    return null;
  }
}

async function acquireLock() {
  const startedAt = Date.now();
  let announcedWait = false;
  while (true) {
    try {
      const handle = await open(lockFile, "wx");
      await handle.writeFile(`${JSON.stringify({ pid: process.pid, started_at: new Date().toISOString() })}\n`, "utf-8");
      return handle;
    } catch (error) {
      if (error?.code !== "EEXIST") {
        throw error;
      }
      const existing = await readLockPayload();
      const existingStartedAt = Date.parse(String(existing?.started_at || ""));
      const staleByPid = existing?.pid && !pidIsRunning(existing.pid);
      const staleByTime = Number.isFinite(existingStartedAt) && ((Date.now() - existingStartedAt) >= lockTimeoutMs);
      if (staleByPid || staleByTime) {
        await rm(lockFile, { force: true }).catch(() => {});
        continue;
      }
      if (!announcedWait) {
        announcedWait = true;
        if (existing) {
          console.log(`prepare-runtime is already running; waiting for lock ${lockFile}. ${JSON.stringify(existing)}`);
        } else {
          console.log(`prepare-runtime is already running; waiting for lock ${lockFile}.`);
        }
      }
      if ((Date.now() - startedAt) >= lockTimeoutMs) {
        throw new Error(`Timed out waiting for prepare-runtime lock: ${lockFile}`);
      }
      await sleep(lockPollIntervalMs);
    }
  }
}

const lockHandle = await acquireLock();

try {
  const completed = spawnSync(
    process.env.JAKAL_FLOW_PYTHON || "python",
    ["-m", "jakal_flow.desktop_runtime_bundle", "--target", targetDir, "--profile", runtimeProfile],
    {
      cwd: repoRoot,
      env,
      stdio: "inherit",
    },
  );

  if (completed.error) {
    throw completed.error;
  }

  process.exit(completed.status ?? 1);
} finally {
  await lockHandle.close().catch(() => {});
  await rm(lockFile, { force: true }).catch(() => {});
}
