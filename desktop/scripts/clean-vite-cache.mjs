import { existsSync, rmSync } from "node:fs";
import { join } from "node:path";

const viteCacheDir = join(process.cwd(), "node_modules", ".vite");

if (existsSync(viteCacheDir)) {
  rmSync(viteCacheDir, { recursive: true, force: true });
}
