import crypto from "node:crypto";
import fs from "node:fs";
import { packagedPath, runtimePaths } from "./paths.mjs";
import { envQuote, writeJson, writeText } from "./util.mjs";

function secret(bytes = 24) {
  return crypto.randomBytes(bytes).toString("hex");
}

function envFile(plan, paths, detection) {
  const dataDir = process.env.PREPPERGPT_DATA_DIR || paths.dataDir;
  const modelsDir = process.env.PREPPERGPT_MODELS_DIR || `${dataDir}/models`;
  const adminPassword = process.env.PREPPERGPT_ADMIN_PASSWORD || secret(18);
  const jupyterToken = process.env.JUPYTER_TOKEN || secret(18);
  const searxngSecret = process.env.SEARXNG_SECRET_KEY || secret(24);
  const lines = {
    PREPPERGPT_PROFILE: plan.profile,
    PREPPERGPT_DATA_DIR: dataDir,
    PREPPERGPT_MODELS_DIR: modelsDir,
    PREPPERGPT_PORT: process.env.PREPPERGPT_PORT || "8080",
    PREPPERGPT_DEFAULT_MODEL: plan.defaultModel,
    PREPPERGPT_MODEL_ORDER_LIST: JSON.stringify(plan.routeIds),
    PREPPERGPT_DOCKER_GPUS: detection.gpus?.length ? "all" : "",
    WEBUI_NAME: "PrepperGPT",
    WEBUI_ADMIN_EMAIL: process.env.WEBUI_ADMIN_EMAIL || "admin@preppergpt.local",
    WEBUI_ADMIN_PASSWORD: adminPassword,
    WEBUI_ADMIN_NAME: process.env.WEBUI_ADMIN_NAME || "PrepperGPT Admin",
    WEBUI_SECRET_KEY: process.env.WEBUI_SECRET_KEY || secret(24),
    JUPYTER_TOKEN: jupyterToken,
    SEARXNG_SECRET_KEY: searxngSecret,
    GLM52_BASE_URL: process.env.GLM52_BASE_URL || "http://127.0.0.1:11441/v1",
    SLOCODE_BASE_URL: process.env.SLOCODE_BASE_URL || "http://127.0.0.1:11438/v1",
    OLLAMA_BASE_URL: process.env.OLLAMA_BASE_URL || "http://127.0.0.1:11434"
  };
  return `${Object.entries(lines)
    .map(([key, value]) => `${key}=${envQuote(value)}`)
    .join("\n")}\n`;
}

function generatedCompose(plan, detection) {
  const modelOrder = JSON.stringify(plan.routeIds);
  const gpuBlock = detection.gpus?.length
    ? [
        "  ollama:",
        "    gpus: all",
        "  local-vision:",
        "    gpus: all"
      ]
    : [];
  return [
    "services:",
    "  open-webui:",
    "    environment:",
    `      DEFAULT_MODELS: "${plan.defaultModel}"`,
    `      MODEL_ORDER_LIST: '${modelOrder.replaceAll("'", "''")}'`,
    `      TASK_MODEL: "${plan.selected.fast?.id || plan.defaultModel}"`,
    ...gpuBlock
  ].join("\n") + "\n";
}

export function renderInstall(plan, detection, options = {}) {
  const paths = runtimePaths(options.home);
  fs.mkdirSync(paths.root, { recursive: true });
  fs.mkdirSync(paths.dataDir, { recursive: true });
  fs.mkdirSync(paths.composeDir, { recursive: true });
  fs.mkdirSync(`${paths.dataDir}/preppergpt`, { recursive: true });
  fs.mkdirSync(`${paths.dataDir}/models`, { recursive: true });
  writeText(paths.envFile, envFile(plan, paths, detection), 0o600);
  writeText(paths.generatedCompose, generatedCompose(plan, detection));
  writeJson(paths.modelPlan, plan);
  writeJson(paths.detectReport, detection);
  return {
    ...paths,
    packageCompose: packagedPath("compose", "preppergpt.yaml")
  };
}
