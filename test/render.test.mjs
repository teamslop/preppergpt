import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { buildPlan, loadCatalog } from "../installer/lib/planner.mjs";
import { renderInstall } from "../installer/lib/render.mjs";

function fixtureDetection() {
  return {
    platform: "linux",
    platformKind: "linux",
    isWsl2: false,
    arch: "x64",
    cpu: { cores: 8, model: "fixture" },
    memory: { totalGb: 32, freeGb: 20 },
    disks: [{ path: "/tmp", mount: "/tmp", freeGb: 200, isNvme: false }],
    gpus: [],
    tools: { docker: true, dockerCompose: true, curl: true, python3: true, python: false, nvidiaSmi: false, rocmSmi: false, rocminfo: false },
    ports: {}
  };
}

function withCleanDesktopEnv(callback) {
  const saved = {
    DISPLAY: process.env.DISPLAY,
    WAYLAND_DISPLAY: process.env.WAYLAND_DISPLAY,
    LOCAL_AGENT_DESKTOP_ENABLED: process.env.LOCAL_AGENT_DESKTOP_ENABLED
  };
  delete process.env.DISPLAY;
  delete process.env.WAYLAND_DISPLAY;
  delete process.env.LOCAL_AGENT_DESKTOP_ENABLED;
  try {
    return callback();
  } finally {
    for (const [key, value] of Object.entries(saved)) {
      if (value === undefined) {
        delete process.env[key];
      } else {
        process.env[key] = value;
      }
    }
  }
}

test("renderInstall writes env, compose override, and plan", () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "preppergpt-test-"));
  const detection = fixtureDetection();
  const plan = buildPlan(detection, "balanced", loadCatalog());
  const paths = renderInstall(plan, detection, { home });

  assert.ok(fs.existsSync(paths.envFile));
  assert.ok(fs.existsSync(paths.generatedCompose));
  assert.ok(fs.existsSync(paths.modelPlan));
  const env = fs.readFileSync(paths.envFile, "utf8");
  assert.match(env, /WEBUI_NAME=PrepperGPT/);
  assert.match(env, /PREPPERGPT_DEFAULT_MODEL=local-chatgpt-auto/);
  assert.match(env, /PREPPERGPT_GLM_MODEL=glm52-q4-local/);
  assert.match(env, /PREPPERGPT_GPU_VENDOR=cpu/);
  assert.match(env, /OLLAMA_IMAGE=ollama\/ollama:latest/);
  assert.match(env, /GLM52_Q8_BASE_URL=http:\/\/127\.0\.0\.1:11446\/v1/);
  assert.match(env, /PREPPERGPT_WHISPER_MODEL=whisper-base/);
  assert.ok(env.includes("PREPPERGPT_WHISPER_MODEL_PATH=/models/whisper/base"));
  const generated = fs.readFileSync(paths.generatedCompose, "utf8");
  assert.match(generated, /DEFAULT_MODELS: "local-chatgpt-auto"/);
});

test("renderInstall emits NVIDIA GPU compose override", () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "preppergpt-test-"));
  const detection = {
    ...fixtureDetection(),
    gpus: [{ index: 0, vendor: "nvidia", runtime: "cuda", name: "fixture gpu", totalVramGb: 24, freeVramGb: 22, usableVramGb: 19.6 }],
    tools: { ...fixtureDetection().tools, nvidiaSmi: true }
  };
  const plan = buildPlan(detection, "speed", loadCatalog());
  const paths = renderInstall(plan, detection, { home });
  const env = fs.readFileSync(paths.envFile, "utf8");
  const generated = fs.readFileSync(paths.generatedCompose, "utf8");
  assert.match(env, /PREPPERGPT_GPU_VENDOR=nvidia/);
  assert.match(env, /PREPPERGPT_DOCKER_GPUS=all/);
  assert.match(generated, /gpus: all/);
});

test("renderInstall emits AMD ROCm compose override", () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "preppergpt-test-"));
  const detection = {
    ...fixtureDetection(),
    gpus: [{ index: 0, vendor: "amd", runtime: "rocm", name: "Radeon fixture", totalVramGb: 24, freeVramGb: 22, usableVramGb: 19.6 }],
    tools: { ...fixtureDetection().tools, rocmSmi: true, rocminfo: true }
  };
  const plan = buildPlan(detection, "speed", loadCatalog());
  const paths = renderInstall(plan, detection, { home });
  const env = fs.readFileSync(paths.envFile, "utf8");
  const generated = fs.readFileSync(paths.generatedCompose, "utf8");
  assert.match(env, /PREPPERGPT_GPU_VENDOR=amd/);
  assert.match(env, /PREPPERGPT_ACCELERATOR=rocm/);
  assert.match(env, /OLLAMA_IMAGE=ollama\/ollama:rocm/);
  assert.match(generated, /\/dev\/kfd:\/dev\/kfd/);
  assert.match(generated, /\/dev\/dri:\/dev\/dri/);
  assert.match(generated, /group_add:/);
  assert.doesNotMatch(generated, /gpus: all/);
});

test("renderInstall keeps WSL2 generated compose free of desktop mounts by default", () => {
  withCleanDesktopEnv(() => {
    const home = fs.mkdtempSync(path.join(os.tmpdir(), "preppergpt-test-"));
    const detection = {
      ...fixtureDetection(),
      platformKind: "wsl2",
      isWsl2: true
    };
    const plan = buildPlan(detection, "balanced", loadCatalog());
    const paths = renderInstall(plan, detection, { home });
    const generated = fs.readFileSync(paths.generatedCompose, "utf8");
    assert.doesNotMatch(generated, /\/tmp\/\.X11-unix/);
    assert.doesNotMatch(generated, /XAUTHORITY/);
  });
});
