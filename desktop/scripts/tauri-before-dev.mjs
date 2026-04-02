import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const desktopRoot = resolve(scriptDir, "..");
const devUrl = "http://127.0.0.1:1420";
const prepareRuntimeScript = join(scriptDir, "prepare-runtime.mjs");
const cleanViteCacheScript = join(scriptDir, "clean-vite-cache.mjs");
const viteBin = join(desktopRoot, "node_modules", "vite", "bin", "vite.js");
const repoRoot = resolve(desktopRoot, "..");
const runtimeManifestPath = join(repoRoot, "rt", "manifest.json");
const runtimeRoot = join(repoRoot, "rt");
const devRuntimePlaceholder = join(runtimeRoot, ".dev-placeholder");

function runBlocking(command, args) {
  const completed = spawnSync(command, args, {
    cwd: desktopRoot,
    stdio: "inherit",
    env: process.env,
  });
  if (completed.error) {
    throw completed.error;
  }
  if ((completed.status ?? 1) !== 0) {
    process.exit(completed.status ?? 1);
  }
}

async function isViteServerReady(url) {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 2500);
    const response = await fetch(url, {
      signal: controller.signal,
      headers: {
        Accept: "text/html",
      },
    });
    clearTimeout(timeout);
    if (!response.ok) {
      return false;
    }
    const body = await response.text();
    return body.includes("/@vite/client") || body.includes("React Refresh");
  } catch {
    return false;
  }
}

async function main() {
  if (String(process.env.JAKAL_FLOW_FORCE_PREPARE_RUNTIME || "").trim() === "1") {
    console.log(`Forced runtime rebuild for dev: ${runtimeManifestPath}.`);
    runBlocking(process.execPath, [prepareRuntimeScript]);
  } else if (!existsSync(runtimeRoot)) {
    mkdirSync(runtimeRoot, { recursive: true });
    writeFileSync(devRuntimePlaceholder, "Dev placeholder for Tauri bundle resources.\n", "utf-8");
    console.log(`Created dev runtime placeholder at ${runtimeRoot}.`);
  } else if (existsSync(runtimeManifestPath)) {
    console.log(`Reusing existing runtime bundle at ${runtimeManifestPath}.`);
  } else {
    console.log(`Reusing existing runtime directory at ${runtimeRoot} without rebuilding the bundle.`);
  }

  if (await isViteServerReady(devUrl)) {
    console.log(`Reusing existing Vite dev server at ${devUrl}.`);
    return;
  }

  runBlocking(process.execPath, [cleanViteCacheScript]);

  const child = spawn(process.execPath, [viteBin, "--host", "0.0.0.0", "--port", "1420"], {
    cwd: desktopRoot,
    stdio: "inherit",
    env: process.env,
  });
  child.on("exit", (code, signal) => {
    if (signal) {
      process.kill(process.pid, signal);
      return;
    }
    process.exit(code ?? 0);
  });
}

await main();
