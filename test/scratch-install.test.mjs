import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { buildPlan, loadCatalog } from "../installer/lib/planner.mjs";
import { packageRoot, runtimePaths } from "../installer/lib/paths.mjs";
import { renderInstall } from "../installer/lib/render.mjs";
import { commandExists, commandResult, readJson } from "../installer/lib/util.mjs";

const catalog = loadCatalog();
const bin = path.join(packageRoot, "bin", "preppergpt.js");
const packagedCompose = path.join(packageRoot, "compose", "preppergpt.yaml");
const canValidateCompose = commandExists("docker") && commandResult("docker", ["compose", "version"], { timeoutMs: 5000 }).ok;

function tempHome(name = "preppergpt-scratch-") {
  return fs.mkdtempSync(path.join(os.tmpdir(), name));
}

function fixtureDetection(overrides = {}) {
  return {
    platform: "linux",
    platformKind: "linux",
    isWsl2: false,
    arch: "x64",
    hostname: "fixture",
    cpu: { cores: 16, model: "fixture" },
    memory: { totalGb: 64, freeGb: 48 },
    disks: [{ path: "/models", mount: "/models", freeGb: 500, isNvme: true }],
    gpus: [],
    tools: {
      docker: true,
      dockerCompose: true,
      curl: true,
      python3: true,
      python: false,
      tmux: true,
      git: true,
      nvidiaSmi: false,
      rocmSmi: false,
      rocminfo: false
    },
    ports: {},
    ...overrides
  };
}

function assertInstallFiles(paths) {
  assert.ok(fs.existsSync(paths.envFile), `${paths.envFile} should exist`);
  assert.ok(fs.existsSync(paths.generatedCompose), `${paths.generatedCompose} should exist`);
  assert.ok(fs.existsSync(paths.modelPlan), `${paths.modelPlan} should exist`);
  assert.ok(fs.existsSync(paths.detectReport), `${paths.detectReport} should exist`);
}

function assertComposeConfig(paths) {
  if (!canValidateCompose) {
    return;
  }
  const result = commandResult(
    "docker",
    ["compose", "--env-file", paths.envFile, "-f", packagedCompose, "-f", paths.generatedCompose, "config"],
    { timeoutMs: 30000 }
  );
  assert.equal(result.ok, true, result.stderr || result.stdout);
}

function renderScratchCase({ profile = "speed", detection }) {
  const home = tempHome();
  const plan = buildPlan(detection, profile, catalog);
  const paths = renderInstall(plan, detection, { home });
  assertInstallFiles(paths);
  assertComposeConfig(paths);
  return { home, paths, plan, env: fs.readFileSync(paths.envFile, "utf8"), generated: fs.readFileSync(paths.generatedCompose, "utf8") };
}

test("local CLI scratch install writes a complete temp home and valid compose", () => {
  const home = tempHome();
  const output = execFileSync(
    process.execPath,
    [bin, "install", "--profile", "speed", "--home", home, "--skip-bundles"],
    { encoding: "utf8" }
  );
  const paths = runtimePaths(home);
  assertInstallFiles(paths);
  assertComposeConfig(paths);
  assert.match(output, /Wrote .*\.env\.preppergpt/);
  assert.match(output, /npx --yes preppergpt start --home/);
  const plan = readJson(paths.modelPlan);
  assert.equal(plan.profile, "speed");
});

test("one-command install/start path is exposed without mutating on dry run", () => {
  const output = execFileSync(
    process.execPath,
    [bin, "install", "--profile", "speed", "--dry-run", "--start"],
    { encoding: "utf8" }
  );
  assert.match(output, /Would start PrepperGPT after install/);
  assert.match(output, /Dry run only/);
});

test("CPU-only scratch install uses CPU-safe compose", () => {
  const { env, generated, plan } = renderScratchCase({
    detection: fixtureDetection({
      memory: { totalGb: 32, freeGb: 20 },
      disks: [{ path: "/home/user/.preppergpt", mount: "/home", freeGb: 80, isNvme: false }]
    })
  });
  assert.equal(plan.selected.fast.id, "llama3.1:8b");
  assert.match(env, /PREPPERGPT_GPU_VENDOR=cpu/);
  assert.doesNotMatch(generated, /gpus: all/);
  assert.doesNotMatch(generated, /\/dev\/kfd/);
});

test("NVIDIA scratch install emits CUDA compose override", () => {
  const { env, generated, plan } = renderScratchCase({
    detection: fixtureDetection({
      gpus: [{ index: 0, vendor: "nvidia", runtime: "cuda", name: "RTX fixture", totalVramGb: 24, freeVramGb: 22, usableVramGb: 19.6 }],
      tools: { ...fixtureDetection().tools, nvidiaSmi: true }
    })
  });
  assert.equal(plan.selected.fast.id, "gemma4:12b-256k-gpu");
  assert.match(env, /PREPPERGPT_GPU_VENDOR=nvidia/);
  assert.match(generated, /gpus: all/);
});

test("AMD ROCm scratch install emits ROCm compose override", () => {
  const { env, generated, plan } = renderScratchCase({
    detection: fixtureDetection({
      gpus: [{ index: 0, vendor: "amd", runtime: "rocm", name: "Radeon fixture", totalVramGb: 24, freeVramGb: 22, usableVramGb: 19.6 }],
      tools: { ...fixtureDetection().tools, rocmSmi: true, rocminfo: true }
    })
  });
  assert.equal(plan.selected.fast.id, "gemma4:12b-256k-gpu");
  assert.match(env, /PREPPERGPT_GPU_VENDOR=amd/);
  assert.match(env, /OLLAMA_IMAGE=ollama\/ollama:rocm/);
  assert.match(generated, /\/dev\/kfd:\/dev\/kfd/);
  assert.match(generated, /\/dev\/dri:\/dev\/dri/);
});

test("AMD without ROCm scratch install falls back to CPU-safe compose", () => {
  const { env, generated, plan } = renderScratchCase({
    detection: fixtureDetection({
      gpus: [{ index: 0, vendor: "amd", runtime: "none", name: "Radeon fixture", totalVramGb: 24, freeVramGb: 22, usableVramGb: 19.6 }]
    })
  });
  assert.equal(plan.selected.fast.id, "llama3.1:8b");
  assert.ok(plan.warnings.some((warning) => warning.includes("AMD GPU detected without ROCm")));
  assert.match(env, /PREPPERGPT_GPU_VENDOR=cpu/);
  assert.doesNotMatch(generated, /\/dev\/kfd/);
});

test("WSL2 scratch install keeps Linux paths and desktop mounts disabled by default", () => {
  const saved = {
    DISPLAY: process.env.DISPLAY,
    WAYLAND_DISPLAY: process.env.WAYLAND_DISPLAY,
    LOCAL_AGENT_DESKTOP_ENABLED: process.env.LOCAL_AGENT_DESKTOP_ENABLED
  };
  delete process.env.DISPLAY;
  delete process.env.WAYLAND_DISPLAY;
  delete process.env.LOCAL_AGENT_DESKTOP_ENABLED;
  try {
    const { generated, paths } = renderScratchCase({
      detection: fixtureDetection({ platformKind: "wsl2", isWsl2: true })
    });
    assert.doesNotMatch(paths.root, /^[A-Za-z]:\\/);
    assert.doesNotMatch(generated, /\/tmp\/\.X11-unix/);
    assert.doesNotMatch(generated, /XAUTHORITY/);
  } finally {
    for (const [key, value] of Object.entries(saved)) {
      if (value === undefined) {
        delete process.env[key];
      } else {
        process.env[key] = value;
      }
    }
  }
});
