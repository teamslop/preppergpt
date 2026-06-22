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
    arch: "x64",
    cpu: { cores: 8, model: "fixture" },
    memory: { totalGb: 32, freeGb: 20 },
    disks: [{ path: "/tmp", mount: "/tmp", freeGb: 200, isNvme: false }],
    gpus: [],
    tools: { docker: true, dockerCompose: true, curl: true, python3: true },
    ports: {}
  };
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
  assert.match(env, /PREPPERGPT_WHISPER_MODEL=whisper-base/);
  assert.ok(env.includes("PREPPERGPT_WHISPER_MODEL_PATH=/models/whisper/base"));
  const generated = fs.readFileSync(paths.generatedCompose, "utf8");
  assert.match(generated, /DEFAULT_MODELS: "local-chatgpt-auto"/);
});
