import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { WHISPER_BUNDLE } from "./bundles.mjs";
import { packagedPath, runtimePaths } from "./paths.mjs";
import { envQuote, writeJson, writeText } from "./util.mjs";

function secret(bytes = 24) {
  return crypto.randomBytes(bytes).toString("hex");
}

function platformKind(detection) {
  return detection.platformKind || (detection.platform === "win32" ? "windows-native" : detection.platform || "unknown");
}

function primaryAccelerator(detection) {
  const gpus = detection.gpus || [];
  const nvidia = gpus.find((gpu) => gpu.vendor === "nvidia");
  if (nvidia) {
    return { vendor: "nvidia", runtime: "cuda" };
  }
  const amdRocm = gpus.find((gpu) => gpu.vendor === "amd" && gpu.runtime === "rocm");
  if (amdRocm && platformKind(detection) === "linux") {
    return { vendor: "amd", runtime: "rocm" };
  }
  return { vendor: "cpu", runtime: "cpu" };
}

function desktopIntegrationEnabled(detection) {
  const explicit = String(process.env.LOCAL_AGENT_DESKTOP_ENABLED || "").toLowerCase();
  if (["0", "false", "no", "off"].includes(explicit)) {
    return false;
  }
  const kind = platformKind(detection);
  const platformSupportsDesktop = kind === "linux" || kind === "wsl2";
  const hasDisplay = Boolean(process.env.DISPLAY || process.env.WAYLAND_DISPLAY);
  return platformSupportsDesktop && hasDisplay && explicit !== "0";
}

function envFile(plan, paths, detection) {
  const dataDir = process.env.PREPPERGPT_DATA_DIR || paths.dataDir;
  const modelsDir = process.env.PREPPERGPT_MODELS_DIR || `${dataDir}/models`;
  const whisperHostDir = path.join(modelsDir, "whisper", "base");
  const accelerator = primaryAccelerator(detection);
  const selectedReasoningModel = plan.selected?.reasoning?.id || "glm52-q4-local";
  const selectedGlmBaseUrl =
    selectedReasoningModel === "glm52-q8-local"
      ? process.env.GLM52_Q8_BASE_URL || "http://127.0.0.1:11446/v1"
      : process.env.GLM52_BASE_URL || "http://127.0.0.1:11441/v1";
  const adminPassword = process.env.PREPPERGPT_ADMIN_PASSWORD || secret(18);
  const jupyterToken = process.env.JUPYTER_TOKEN || secret(18);
  const searxngSecret = process.env.SEARXNG_SECRET_KEY || secret(24);
  const lines = {
    PREPPERGPT_PROFILE: plan.profile,
    PREPPERGPT_DATA_DIR: dataDir,
    PREPPERGPT_MODELS_DIR: modelsDir,
    PREPPERGPT_WHISPER_HOST_DIR: whisperHostDir,
    PREPPERGPT_WHISPER_MODEL: WHISPER_BUNDLE.id,
    PREPPERGPT_WHISPER_MODEL_PATH: WHISPER_BUNDLE.modelPathInContainer,
    PREPPERGPT_PORT: process.env.PREPPERGPT_PORT || "8080",
    PREPPERGPT_DEFAULT_MODEL: plan.defaultModel,
    PREPPERGPT_MODEL_ORDER_LIST: JSON.stringify(plan.routeIds),
    PREPPERGPT_GLM_MODEL: selectedReasoningModel,
    PREPPERGPT_GLM_BASE_URL: selectedGlmBaseUrl,
    PREPPERGPT_GPU_VENDOR: accelerator.vendor,
    PREPPERGPT_ACCELERATOR: accelerator.runtime,
    PREPPERGPT_DOCKER_GPUS: accelerator.vendor === "nvidia" ? "all" : "",
    OLLAMA_IMAGE: accelerator.vendor === "amd" ? "ollama/ollama:rocm" : "ollama/ollama:latest",
    WEBUI_NAME: "PrepperGPT",
    WEBUI_ADMIN_EMAIL: process.env.WEBUI_ADMIN_EMAIL || "admin@preppergpt.local",
    WEBUI_ADMIN_PASSWORD: adminPassword,
    WEBUI_ADMIN_NAME: process.env.WEBUI_ADMIN_NAME || "PrepperGPT Admin",
    WEBUI_SECRET_KEY: process.env.WEBUI_SECRET_KEY || secret(24),
    JUPYTER_TOKEN: jupyterToken,
    SEARXNG_SECRET_KEY: searxngSecret,
    GLM52_BASE_URL: process.env.GLM52_BASE_URL || "http://127.0.0.1:11441/v1",
    GLM52_Q8_BASE_URL: process.env.GLM52_Q8_BASE_URL || "http://127.0.0.1:11446/v1",
    SLOCODE_BASE_URL: process.env.SLOCODE_BASE_URL || "http://127.0.0.1:11438/v1",
    OLLAMA_BASE_URL: process.env.OLLAMA_BASE_URL || "http://127.0.0.1:11434"
  };
  return `${Object.entries(lines)
    .map(([key, value]) => `${key}=${envQuote(value)}`)
    .join("\n")}\n`;
}

function generatedCompose(plan, detection) {
  const modelOrder = JSON.stringify(plan.routeIds);
  const accelerator = primaryAccelerator(detection);
  const gpuBlock =
    accelerator.vendor === "nvidia"
      ? [
        "  ollama:",
        "    gpus: all",
        "  local-vision:",
        "    gpus: all"
      ]
      : accelerator.vendor === "amd"
        ? [
            "  ollama:",
            "    devices:",
            "      - /dev/kfd:/dev/kfd",
            "      - /dev/dri:/dev/dri",
            "    group_add:",
            "      - video",
            "      - render",
            "    security_opt:",
            "      - seccomp=unconfined"
          ]
        : [];
  const desktopBlock = desktopIntegrationEnabled(detection)
    ? [
        "  local-agent:",
        "    environment:",
        "      LOCAL_AGENT_DESKTOP_ENABLED: \"1\"",
        "    volumes:",
        "      - /tmp/.X11-unix:/tmp/.X11-unix:rw",
        "      - ${XDG_RUNTIME_DIR:-/run/user/1000}:${XDG_RUNTIME_DIR:-/run/user/1000}:rw",
        "      - ${XAUTHORITY:-/tmp/.preppergpt-missing-xauthority}:/tmp/.Xauthority:ro"
      ]
    : [];
  return [
    "services:",
    "  open-webui:",
    "    environment:",
    `      DEFAULT_MODELS: "${plan.defaultModel}"`,
    `      MODEL_ORDER_LIST: '${modelOrder.replaceAll("'", "''")}'`,
    `      TASK_MODEL: "${plan.selected.fast?.id || plan.defaultModel}"`,
    ...gpuBlock,
    ...desktopBlock
  ].join("\n") + "\n";
}

export function renderInstall(plan, detection, options = {}) {
  const paths = runtimePaths(options.home);
  const dataDir = process.env.PREPPERGPT_DATA_DIR || paths.dataDir;
  const modelsDir = process.env.PREPPERGPT_MODELS_DIR || `${dataDir}/models`;
  const whisperHostDir = path.join(modelsDir, "whisper", "base");
  fs.mkdirSync(paths.root, { recursive: true });
  fs.mkdirSync(paths.dataDir, { recursive: true });
  fs.mkdirSync(paths.composeDir, { recursive: true });
  fs.mkdirSync(`${paths.dataDir}/preppergpt`, { recursive: true });
  fs.mkdirSync(modelsDir, { recursive: true });
  fs.mkdirSync(whisperHostDir, { recursive: true });
  writeText(paths.envFile, envFile(plan, paths, detection), 0o600);
  writeText(paths.generatedCompose, generatedCompose(plan, detection));
  writeJson(paths.modelPlan, plan);
  writeJson(paths.detectReport, detection);
  return {
    ...paths,
    modelsDir,
    whisperHostDir,
    packageCompose: packagedPath("compose", "preppergpt.yaml")
  };
}
