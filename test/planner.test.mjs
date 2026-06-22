import assert from "node:assert/strict";
import test from "node:test";
import { buildPlan, installSupportError, loadCatalog, normalizeProfile } from "../installer/lib/planner.mjs";

const catalog = loadCatalog();

function detection(overrides = {}) {
  return {
    platform: "linux",
    platformKind: "linux",
    isWsl2: false,
    arch: "x64",
    cpu: { cores: 24, model: "fixture" },
    memory: { totalGb: 128, freeGb: 96 },
    disks: [{ path: "/models", mount: "/models", freeGb: 1000, isNvme: true }],
    gpus: [{ index: 0, vendor: "nvidia", name: "fixture gpu", totalVramGb: 24, freeVramGb: 22, usableVramGb: 19.6 }],
    tools: {
      docker: true,
      dockerCompose: true,
      curl: true,
      python3: true,
      python: false,
      tmux: true,
      git: true,
      nvidiaSmi: true,
      rocmSmi: false,
      rocminfo: false
    },
    ports: {},
    ...overrides
  };
}

test("normalizes profile aliases", () => {
  assert.equal(normalizeProfile("max-intelligence"), "intelligence");
  assert.equal(normalizeProfile("middle-ground"), "balanced");
  assert.equal(normalizeProfile("fast"), "speed");
});

test("balanced plan keeps auto route as default and includes specialist routes", () => {
  const plan = buildPlan(detection(), "balanced", catalog);
  assert.equal(plan.defaultModel, "local-chatgpt-auto");
  assert.equal(plan.selected.fast.id, "gemma4:12b-256k-gpu");
  assert.equal(plan.selected.coding.id, "qwen3.6-35b-a3b:slopcode-cpu-64k");
  assert.equal(plan.selected.stt.id, "whisper-base-bundled");
  assert.ok(plan.routeIds.includes("local-chatgpt-auto"));
  assert.ok(plan.routeIds.includes("glm52-q4-local"));
  assert.ok(plan.routeIds.includes("whisper-base-bundled"));
});

test("intelligence plan prioritizes GLM 5.2 long context", () => {
  const plan = buildPlan(detection(), "intelligence", catalog);
  assert.equal(plan.defaultModel, "glm52-q4-local");
  assert.equal(plan.selected.chat.id, "glm52-q4-local");
  assert.equal(plan.estimates.maxContextTokens, 262144);
  assert.ok(plan.manualAssets.some((asset) => asset.id === "glm52-q4-local"));
});

test("enterprise intelligence plan upgrades to GLM 5.2 Q8 when hardware fits", () => {
  const plan = buildPlan(
    detection({
      memory: { totalGb: 256, freeGb: 180 },
      disks: [{ path: "/models", mount: "/models", freeGb: 1800, isNvme: true }],
      gpus: [{ index: 0, vendor: "nvidia", name: "enterprise gpu", totalVramGb: 80, freeVramGb: 70, usableVramGb: 65 }]
    }),
    "intelligence",
    catalog
  );
  assert.equal(plan.defaultModel, "glm52-q8-local");
  assert.equal(plan.selected.chat.id, "glm52-q8-local");
  assert.equal(plan.selected.reasoning.id, "glm52-q8-local");
  assert.ok(plan.routeIds.includes("glm52-q8-local"));
});

test("enterprise balanced plan keeps auto default but routes hard reasoning to Q8", () => {
  const plan = buildPlan(
    detection({
      memory: { totalGb: 256, freeGb: 180 },
      disks: [{ path: "/models", mount: "/models", freeGb: 1800, isNvme: true }],
      gpus: [{ index: 0, vendor: "nvidia", name: "enterprise gpu", totalVramGb: 80, freeVramGb: 70, usableVramGb: 65 }]
    }),
    "balanced",
    catalog
  );
  assert.equal(plan.defaultModel, "local-chatgpt-auto");
  assert.equal(plan.selected.reasoning.id, "glm52-q8-local");
});

test("speed plan can fall back on small Ollama route for CPU-only machines", () => {
  const plan = buildPlan(
    detection({
      memory: { totalGb: 32, freeGb: 20 },
      disks: [{ path: "/home/user/.preppergpt", mount: "/home", freeGb: 80, isNvme: false }],
      gpus: []
    }),
    "speed",
    catalog
  );
  assert.equal(plan.defaultModel, "local-chatgpt-auto");
  assert.equal(plan.selected.fast.id, "llama3.1:8b");
  assert.ok(plan.warnings.some((warning) => warning.includes("No supported GPU acceleration")));
});

test("AMD ROCm machines can use accelerated Ollama routes", () => {
  const plan = buildPlan(
    detection({
      gpus: [{ index: 0, vendor: "amd", runtime: "rocm", name: "Radeon fixture", totalVramGb: 24, freeVramGb: 22, usableVramGb: 19.6 }],
      tools: {
        docker: true,
        dockerCompose: true,
        curl: true,
        python3: true,
        python: false,
        tmux: true,
        git: true,
        nvidiaSmi: false,
        rocmSmi: true,
        rocminfo: true
      }
    }),
    "speed",
    catalog
  );
  assert.equal(plan.selected.fast.id, "gemma4:12b-256k-gpu");
  assert.equal(plan.selected.coding.id, "qwen2.5-coder:14b");
  assert.ok(!plan.warnings.some((warning) => warning.includes("No supported GPU acceleration")));
});

test("AMD without ROCm falls back to CPU-compatible routes with ROCm warning", () => {
  const plan = buildPlan(
    detection({
      gpus: [{ index: 0, vendor: "amd", runtime: "none", name: "Radeon fixture", totalVramGb: 24, freeVramGb: 22, usableVramGb: 19.6 }],
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
      }
    }),
    "speed",
    catalog
  );
  assert.equal(plan.selected.fast.id, "llama3.1:8b");
  assert.ok(plan.warnings.some((warning) => warning.includes("AMD GPU detected without ROCm")));
});

test("WSL2 is supported but AMD acceleration remains Linux ROCm only", () => {
  const plan = buildPlan(
    detection({
      platformKind: "wsl2",
      isWsl2: true,
      gpus: [{ index: 0, vendor: "amd", runtime: "rocm", name: "Radeon fixture", totalVramGb: 24, freeVramGb: 22, usableVramGb: 19.6 }],
      tools: {
        docker: true,
        dockerCompose: true,
        curl: true,
        python3: true,
        python: false,
        tmux: true,
        git: true,
        nvidiaSmi: false,
        rocmSmi: true,
        rocminfo: true
      }
    }),
    "speed",
    catalog
  );
  assert.equal(installSupportError({ platform: "linux", platformKind: "wsl2" }), null);
  assert.equal(plan.selected.fast.id, "llama3.1:8b");
  assert.ok(plan.warnings.some((warning) => warning.includes("AMD GPU acceleration is supported on Linux ROCm hosts")));
});

test("native Windows install is rejected with WSL2 guidance", () => {
  const message = installSupportError(detection({ platform: "win32", platformKind: "windows-native" }));
  assert.match(message, /WSL2/);
});
