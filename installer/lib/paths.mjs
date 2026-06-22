import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

export function defaultHome() {
  return path.resolve(process.env.PREPPERGPT_HOME || path.join(os.homedir(), ".preppergpt"));
}

export function runtimePaths(home = defaultHome()) {
  const root = path.resolve(home);
  return {
    root,
    envFile: path.join(root, ".env.preppergpt"),
    dataDir: path.join(root, "data"),
    composeDir: path.join(root, "compose"),
    generatedCompose: path.join(root, "compose", "generated.models.yaml"),
    modelPlan: path.join(root, "data", "preppergpt", "model-plan.json"),
    detectReport: path.join(root, "data", "preppergpt", "hardware-detect.json"),
    setupState: path.join(root, "data", "preppergpt", "setup-state.json"),
    setupLog: path.join(root, "data", "preppergpt", "setup.log")
  };
}

export function packagedPath(...parts) {
  return path.join(packageRoot, ...parts);
}
