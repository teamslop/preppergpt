import assert from "node:assert/strict";
import test from "node:test";
import { buildPlan, loadCatalog, normalizeProfile } from "../installer/lib/planner.mjs";

const catalog = loadCatalog();

function detection(overrides = {}) {
  return {
    platform: "linux",
    arch: "x64",
    cpu: { cores: 24, model: "fixture" },
    memory: { totalGb: 128, freeGb: 96 },
    disks: [{ path: "/models", mount: "/models", freeGb: 1000, isNvme: true }],
    gpus: [{ index: 0, vendor: "nvidia", name: "fixture gpu", totalVramGb: 24, freeVramGb: 22, usableVramGb: 19.6 }],
    tools: { docker: true, dockerCompose: true, curl: true, python3: true, tmux: true, git: true, nvidiaSmi: true },
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
  assert.ok(plan.warnings.some((warning) => warning.includes("No NVIDIA GPU")));
});
