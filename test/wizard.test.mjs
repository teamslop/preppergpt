import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { runtimePaths } from "../installer/lib/paths.mjs";
import { commandExists, commandResult, readJson } from "../installer/lib/util.mjs";
import {
  beginnerDoctorSummary,
  chooseAutoProfile,
  runWizard
} from "../installer/lib/wizard.mjs";

const bin = path.resolve("bin/preppergpt.js");
const canValidateCompose = commandExists("docker") && commandResult("docker", ["compose", "version"], { timeoutMs: 5000 }).ok;

function tempHome() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "preppergpt-wizard-"));
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

test("chooseAutoProfile picks beginner-safe defaults by hardware", () => {
  assert.equal(chooseAutoProfile(fixtureDetection({ memory: { totalGb: 16, freeGb: 8 } })), "speed");
  assert.equal(
    chooseAutoProfile(
      fixtureDetection({
        gpus: [{ vendor: "nvidia", runtime: "cuda", name: "RTX fixture", usableVramGb: 16 }]
      })
    ),
    "balanced"
  );
  assert.equal(
    chooseAutoProfile(
      fixtureDetection({
        memory: { totalGb: 256, freeGb: 200 },
        disks: [{ path: "/models", mount: "/models", freeGb: 1800, isNvme: true }]
      })
    ),
    "intelligence"
  );
});

test("beginnerDoctorSummary separates blockers from optional notes", () => {
  const detection = fixtureDetection({ tools: { ...fixtureDetection().tools, docker: false } });
  const summary = beginnerDoctorSummary(detection, {
    warnings: [
      "No supported GPU acceleration detected; CPU fallback will be much slower.",
      "Some selected high-quality routes need manual model files or already-running external endpoints."
    ],
    profile: "speed",
    defaultModel: "local-chatgpt-auto",
    routeIds: ["local-chatgpt-auto"],
    manualAssets: [],
    estimates: { maxContextTokens: 8192 }
  });
  assert.equal(summary.ready, false);
  assert.ok(summary.blockers.some((blocker) => blocker.issue.includes("Docker")));
  assert.equal(summary.notes.length, 2);
});

test("runWizard writes resumable setup state, log, and install artifacts", async () => {
  const home = tempHome();
  const detection = fixtureDetection({
    gpus: [{ vendor: "nvidia", runtime: "cuda", name: "RTX fixture", totalVramGb: 24, freeVramGb: 20, usableVramGb: 19.6 }],
    tools: { ...fixtureDetection().tools, nvidiaSmi: true }
  });
  const { state, paths } = await runWizard(
    { home, yes: true, profile: "auto", skip_bundles: true, quiet: true },
    { detectMachine: async () => detection }
  );
  assert.equal(state.status, "complete");
  assert.equal(state.selectedProfile, "balanced");
  assert.equal(state.steps.find((step) => step.id === "bundle-whisper").status, "skipped");
  assert.equal(state.steps.find((step) => step.id === "start").status, "skipped");
  assert.ok(fs.existsSync(paths.setupState));
  assert.ok(fs.existsSync(paths.setupLog));
  assert.ok(fs.existsSync(paths.envFile));
  assert.ok(fs.existsSync(paths.generatedCompose));
  assert.ok(fs.existsSync(paths.modelPlan));
  if (canValidateCompose) {
    const result = commandResult(
      "docker",
      ["compose", "--env-file", paths.envFile, "-f", path.resolve("compose/preppergpt.yaml"), "-f", paths.generatedCompose, "config"],
      { timeoutMs: 30000 }
    );
    assert.equal(result.ok, true, result.stderr || result.stdout);
  }
});

test("runWizard resumes failed steps without redoing completed work", async () => {
  const home = tempHome();
  const detection = fixtureDetection();
  await runWizard({ home, yes: true, profile: "speed", skip_bundles: true, quiet: true }, { detectMachine: async () => detection });
  const paths = runtimePaths(home);
  const state = readJson(paths.setupState);
  state.status = "failed";
  state.lastError = "download interrupted";
  state.steps.find((step) => step.id === "bundle-whisper").status = "failed";
  fs.writeFileSync(paths.setupState, `${JSON.stringify(state, null, 2)}\n`);

  const resumed = await runWizard({ home, yes: true, profile: "speed", skip_bundles: true, resume: true, quiet: true }, {
    detectMachine: async () => {
      throw new Error("detect should have been skipped from saved state");
    }
  });
  assert.equal(resumed.state.status, "complete");
  assert.equal(resumed.state.steps.find((step) => step.id === "detect").status, "done");
  assert.equal(resumed.state.steps.find((step) => step.id === "bundle-whisper").status, "skipped");
});

test("runWizard reset ignores previous failed state", async () => {
  const home = tempHome();
  const paths = runtimePaths(home);
  fs.mkdirSync(path.dirname(paths.setupState), { recursive: true });
  fs.writeFileSync(paths.setupState, JSON.stringify({ schemaVersion: 1, status: "failed", steps: [] }, null, 2));
  const result = await runWizard(
    { home, yes: true, profile: "speed", skip_bundles: true, reset: true, quiet: true },
    { detectMachine: async () => fixtureDetection() }
  );
  assert.equal(result.state.status, "complete");
  assert.equal(result.state.lastError, null);
  assert.equal(result.state.steps.find((step) => step.id === "detect").status, "done");
});

test("CLI wizard JSON run works in a clean temp home", () => {
  const home = tempHome();
  const output = execFileSync(
    process.execPath,
    [bin, "wizard", "--yes", "--profile", "speed", "--home", home, "--skip-bundles", "--json"],
    { encoding: "utf8" }
  );
  const state = JSON.parse(output);
  assert.equal(state.status, "complete");
  assert.equal(state.selectedProfile, "speed");
  assert.ok(fs.existsSync(runtimePaths(home).setupState));
});
