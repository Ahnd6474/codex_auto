import { copyFileSync, mkdirSync, readdirSync, readFileSync } from "node:fs";
import { basename, extname, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import process from "node:process";
import { dirname } from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const desktopRoot = resolve(__dirname, "..");
const repoRoot = resolve(desktopRoot, "..");
const targetBundleRoot = join(desktopRoot, "src-tauri", "target", "release", "bundle");
const releaseRoot = join(repoRoot, "release");
const leanConfigPath = join(desktopRoot, "src-tauri", "tauri.lean.conf.json");

export function normalizeVariant(value) {
  const variant = String(value || "").trim().toLowerCase();
  if (!variant) {
    return "full";
  }
  if (!["full", "python", "lean", "all"].includes(variant)) {
    throw new Error(`Unsupported desktop release variant: ${value}`);
  }
  return variant;
}

export function releaseNameForVariant(fileName, variant) {
  if (variant === "full") {
    return fileName;
  }
  const extension = extname(fileName);
  const stem = basename(fileName, extension);
  return `${stem}_${variant}${extension}`;
}

export function tauriBuildArgs(variant) {
  const normalized = normalizeVariant(variant);
  if (normalized === "full" || normalized === "python") {
    return ["build"];
  }
  if (normalized === "lean") {
    return ["build", "--config", leanConfigPath];
  }
  throw new Error(`Unsupported desktop release variant: ${variant}`);
}

function npmExecutable() {
  return process.platform === "win32" ? "npm.cmd" : "npm";
}

function tauriExecutable() {
  return process.platform === "win32"
    ? join(desktopRoot, "node_modules", ".bin", "tauri.cmd")
    : join(desktopRoot, "node_modules", ".bin", "tauri");
}

function runCommand(command, args, cwd) {
  const lowerCommand = command.toLowerCase();
  const requiresShell = lowerCommand.endsWith(".cmd") || lowerCommand.endsWith(".bat");
  const completed = spawnSync(command, args, {
    cwd,
    stdio: "inherit",
    env: process.env,
    shell: requiresShell,
  });
  if (completed.error) {
    throw completed.error;
  }
  if ((completed.status ?? 1) !== 0) {
    throw new Error(`Command failed: ${command} ${args.join(" ")}`);
  }
}

function packageVersion() {
  const payload = JSON.parse(readFileSync(join(desktopRoot, "package.json"), "utf-8"));
  return String(payload.version || "").trim() || "0.0.0";
}

function bundleArtifacts() {
  const artifacts = [];
  for (const bundleDir of ["msi", "nsis"]) {
    const directory = join(targetBundleRoot, bundleDir);
    try {
      for (const fileName of readdirSync(directory)) {
        const lower = fileName.toLowerCase();
        if (lower.endsWith(".msi") || lower.endsWith(".exe")) {
          artifacts.push(join(directory, fileName));
        }
      }
    } catch {
      continue;
    }
  }
  return artifacts.sort();
}

export function releaseCopyPlan(fileNames, variant) {
  return fileNames.map((fileName) => ({
    sourceName: fileName,
    targetName: releaseNameForVariant(fileName, variant),
  }));
}

function copyReleaseArtifacts(variant) {
  mkdirSync(releaseRoot, { recursive: true });
  const artifacts = bundleArtifacts();
  if (artifacts.length === 0) {
    throw new Error("No desktop bundle artifacts were produced.");
  }
  for (const artifactPath of artifacts) {
    const targetName = releaseNameForVariant(basename(artifactPath), variant);
    copyFileSync(artifactPath, join(releaseRoot, targetName));
  }
}

function buildVariant(variant) {
  if (variant === "full" || variant === "python") {
    runCommand(npmExecutable(), ["run", "prepare:runtime", "--", "--profile", variant], desktopRoot);
  }
  runCommand(tauriExecutable(), tauriBuildArgs(variant), desktopRoot);
  copyReleaseArtifacts(variant);
}

function main(argv = process.argv.slice(2)) {
  const variant = normalizeVariant(argv[0] || "full");
  if (variant === "all") {
    buildVariant("full");
    buildVariant("python");
    buildVariant("lean");
    console.log(`Built desktop release variants for ${packageVersion()}: full, python, lean`);
    return 0;
  }
  buildVariant(variant);
  console.log(`Built desktop ${variant} release for ${packageVersion()}`);
  return 0;
}

if (process.argv[1] === __filename) {
  process.exit(main());
}
