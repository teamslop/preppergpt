import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import readline from "node:readline/promises";
import { stdin as input, stdout as output } from "node:process";
import { ensureWhisperBundle, whisperBundleStatus } from "./bundles.mjs";
import { detectMachine } from "./detect.mjs";
import { buildPlan, installSupportError, normalizeProfile } from "./planner.mjs";
import { packageRoot, runtimePaths } from "./paths.mjs";
import { commandResult, readJson, shellQuote, writeJson } from "./util.mjs";
import { renderInstall } from "./render.mjs";

const STEP_DEFINITIONS = [
  ["detect", "Checking this computer"],
  ["system-check", "Checking required tools"],
  ["profile", "Choosing a setup mode"],
  ["plan", "Planning local models"],
  ["render", "Writing configuration"],
  ["bundle-whisper", "Preparing speech-to-text"],
  ["start", "Starting services"],
  ["health", "Checking service status"]
];

function now() {
  return new Date().toISOString();
}

function boolFlag(value) {
  return value === true || value === "true" || value === "1" || value === "yes";
}

function skipBundleFlag(flags) {
  return boolFlag(flags.skip_bundles) || boolFlag(flags.skip_large_models) || boolFlag(flags.skip_downloads);
}

function selectedGpu(detection) {
  return [...(detection.gpus || [])].sort((a, b) => (b.usableVramGb || 0) - (a.usableVramGb || 0))[0] || null;
}

function bestDisk(detection) {
  return [...(detection.disks || [])].sort((a, b) => (b.freeGb || 0) - (a.freeGb || 0))[0] || null;
}

export function chooseAutoProfile(detection) {
  const disk = bestDisk(detection);
  const gpu = selectedGpu(detection);
  const hasAcceleration =
    gpu?.vendor === "nvidia" || (gpu?.vendor === "amd" && gpu?.runtime === "rocm" && detection.platformKind === "linux");
  if (detection.memory?.totalGb >= 192 && disk?.freeGb >= 1000 && disk?.isNvme) {
    return "intelligence";
  }
  if (!hasAcceleration || detection.memory?.totalGb < 32) {
    return "speed";
  }
  return "balanced";
}

export function summarizeDetection(detection) {
  const gpu = selectedGpu(detection);
  const disk = bestDisk(detection);
  return {
    platform: detection.platformKind || detection.platform || "unknown",
    cpuCores: detection.cpu?.cores || 0,
    ramGb: detection.memory?.totalGb || 0,
    diskFreeGb: disk?.freeGb || 0,
    diskPath: disk?.mount || disk?.path || "",
    gpu: gpu ? `${gpu.vendor}/${gpu.runtime || "unknown"} ${gpu.name}` : "CPU only"
  };
}

export function summarizePlan(plan) {
  return {
    profile: plan.profile,
    defaultModel: plan.defaultModel,
    routeCount: plan.routeIds.length,
    maxContextTokens: plan.estimates.maxContextTokens,
    manualAssets: plan.manualAssets.map((asset) => asset.id),
    warnings: plan.warnings
  };
}

export function beginnerFixFor(message = "") {
  const text = String(message);
  if (/Native Windows/i.test(text)) {
    return "Install Ubuntu in WSL2, enable Docker Desktop WSL integration, then run the wizard inside the WSL2 shell.";
  }
  if (/dockerCompose|Docker Compose|docker compose/i.test(text)) {
    return "Install Docker with Docker Compose, start Docker, then rerun: npx --yes preppergpt wizard --resume";
  }
  if (/\bdocker\b/i.test(text)) {
    return "Install and start Docker, then rerun: npx --yes preppergpt wizard --resume";
  }
  if (/python/i.test(text)) {
    return "Install Python 3, then rerun: npx --yes preppergpt wizard --resume";
  }
  if (/curl/i.test(text)) {
    return "Install curl, then rerun: npx --yes preppergpt wizard --resume";
  }
  if (/Ports already in use/i.test(text)) {
    return "Stop the service using the listed port or set PREPPERGPT_PORT before rerunning the wizard.";
  }
  if (/ROCm/i.test(text)) {
    return "Install ROCm on Linux for AMD acceleration, or continue with CPU-compatible routes.";
  }
  if (/manual model|manual assets|external endpoint|manual or external/i.test(text)) {
    return "You can use PrepperGPT now with available local routes; optional advanced models can be added later.";
  }
  if (/disk|space/i.test(text)) {
    return "Free disk space or choose a larger PREPPERGPT_HOME/PREPPERGPT_MODELS_DIR location, then rerun the wizard.";
  }
  return "Fix the issue above, then rerun: npx --yes preppergpt wizard --resume";
}

export function beginnerDoctorSummary(detection, plan) {
  const blockers = [];
  const notes = [];
  const supportError = installSupportError(detection);
  if (supportError) {
    blockers.push({ issue: supportError, fix: beginnerFixFor(supportError) });
  }
  const tools = detection.tools || {};
  for (const [tool, present] of Object.entries({
    Docker: tools.docker,
    "Docker Compose": tools.dockerCompose,
    "Python 3": tools.python3 || tools.python,
    curl: tools.curl
  })) {
    if (!present) {
      blockers.push({ issue: `${tool} is missing.`, fix: beginnerFixFor(tool) });
    }
  }
  for (const warning of plan?.warnings || []) {
    if (/Ports already in use/i.test(warning)) {
      blockers.push({ issue: warning, fix: beginnerFixFor(warning) });
    } else if (/ROCm|manual|external|No supported GPU/i.test(warning)) {
      notes.push({ issue: warning, fix: beginnerFixFor(warning) });
    }
  }
  return {
    ready: blockers.length === 0,
    blockers,
    notes,
    hardware: summarizeDetection(detection),
    plan: plan ? summarizePlan(plan) : null
  };
}

function createState(paths, flags) {
  return {
    schemaVersion: 1,
    status: "running",
    createdAt: now(),
    updatedAt: now(),
    home: paths.root,
    requestedProfile: flags.profile || "auto",
    selectedProfile: null,
    currentStep: null,
    steps: STEP_DEFINITIONS.map(([id, title]) => ({ id, title, status: "pending" })),
    artifacts: {
      state: paths.setupState,
      log: paths.setupLog,
      env: paths.envFile,
      compose: paths.generatedCompose,
      modelPlan: paths.modelPlan,
      hardwareReport: paths.detectReport
    },
    lastError: null,
    nextAction: null
  };
}

export function loadSetupState(paths) {
  if (!fs.existsSync(paths.setupState)) {
    return null;
  }
  return readJson(paths.setupState);
}

function mergeState(state) {
  const known = new Map((state.steps || []).map((step) => [step.id, step]));
  return {
    ...state,
    steps: STEP_DEFINITIONS.map(([id, title]) => known.get(id) || { id, title, status: "pending" })
  };
}

function saveState(paths, state, dryRun = false) {
  state.updatedAt = now();
  if (!dryRun) {
    writeJson(paths.setupState, state);
  }
}

function appendLog(paths, message, dryRun = false) {
  if (dryRun) {
    return;
  }
  fs.mkdirSync(path.dirname(paths.setupLog), { recursive: true });
  fs.appendFileSync(paths.setupLog, `[${now()}] ${message}\n`);
}

function stepEntry(state, id) {
  return state.steps.find((step) => step.id === id);
}

function isDone(state, id) {
  return stepEntry(state, id)?.status === "done" || stepEntry(state, id)?.status === "skipped";
}

function markStep(state, id, status, details = {}) {
  const step = stepEntry(state, id);
  if (!step) {
    return;
  }
  Object.assign(step, details, { status });
  if (status === "running") {
    step.startedAt = step.startedAt || now();
  }
  if (["done", "failed", "skipped"].includes(status)) {
    step.completedAt = now();
  }
}

function outputLine(flags, line, stream = process.stdout) {
  if (boolFlag(flags.json) || boolFlag(flags.quiet)) {
    return;
  }
  stream.write(`${line}\n`);
}

async function ask(flags, question, defaultValue, choices = null) {
  if (boolFlag(flags.yes) || !process.stdin.isTTY) {
    return defaultValue;
  }
  const rl = readline.createInterface({ input, output });
  try {
    const suffix = choices ? ` (${choices.join("/")}, default ${defaultValue})` : ` (default ${defaultValue})`;
    const answer = (await rl.question(`${question}${suffix}: `)).trim();
    if (!answer) {
      return defaultValue;
    }
    return answer;
  } finally {
    rl.close();
  }
}

function normalizeWizardProfile(value, detection) {
  const raw = String(value || "auto").toLowerCase();
  if (raw === "auto") {
    return chooseAutoProfile(detection);
  }
  return normalizeProfile(raw);
}

function runCompose(paths, args) {
  const result = commandResult("docker", [
    "compose",
    "--env-file",
    paths.envFile,
    "-f",
    `${packageRoot}/compose/preppergpt.yaml`,
    "-f",
    paths.generatedCompose,
    ...args
  ], { timeoutMs: 120000 });
  if (!result.ok) {
    throw new Error(result.stderr || result.stdout || `docker compose ${args.join(" ")} failed`);
  }
  return result;
}

async function fetchStatus(url) {
  return new Promise((resolve) => {
    const req = http.get(url, { timeout: 4000 }, (res) => {
      res.resume();
      res.on("end", () => resolve({ url, ok: res.statusCode >= 200 && res.statusCode < 500, status: res.statusCode }));
    });
    req.on("timeout", () => {
      req.destroy();
      resolve({ url, ok: false, status: "timeout" });
    });
    req.on("error", () => resolve({ url, ok: false, status: "down" }));
  });
}

async function runStep({ id, state, paths, flags, total, index, action, context }) {
  const step = stepEntry(state, id);
  if (isDone(state, id)) {
    outputLine(flags, `[${index}/${total}] ${step.title}: already done`);
    return context;
  }
  outputLine(flags, `[${index}/${total}] ${step.title}`);
  markStep(state, id, "running");
  state.currentStep = id;
  state.status = "running";
  saveState(paths, state, boolFlag(flags.dry_run));
  appendLog(paths, `START ${id}`, boolFlag(flags.dry_run));
  try {
    const result = await action(context);
    const finalStatus = result?.step?.status || "done";
    markStep(state, id, finalStatus, result?.step || {});
    state.lastError = null;
    state.nextAction = null;
    appendLog(paths, `DONE ${id}`, boolFlag(flags.dry_run));
    saveState(paths, state, boolFlag(flags.dry_run));
    return { ...context, ...(result?.context || {}) };
  } catch (error) {
    const message = error?.message || String(error);
    const nextAction = beginnerFixFor(message);
    markStep(state, id, "failed", { error: message, nextAction });
    state.status = "failed";
    state.lastError = message;
    state.nextAction = nextAction;
    appendLog(paths, `FAILED ${id}: ${message}`, boolFlag(flags.dry_run));
    saveState(paths, state, boolFlag(flags.dry_run));
    throw error;
  }
}

function stateForJson(state) {
  const copy = JSON.parse(JSON.stringify(state));
  delete copy.detection;
  return copy;
}

export async function runWizard(flags = {}, deps = {}) {
  const paths = runtimePaths(flags.home);
  if (boolFlag(flags.reset) && fs.existsSync(paths.setupState) && !boolFlag(flags.dry_run)) {
    fs.rmSync(paths.setupState, { force: true });
  }
  const previous = loadSetupState(paths);
  const state = previous && !boolFlag(flags.reset) ? mergeState(previous) : createState(paths, flags);
  const dryRun = boolFlag(flags.dry_run);
  const total = STEP_DEFINITIONS.length;
  const shouldStart = boolFlag(flags.start);
  const shouldBundle = !skipBundleFlag(flags);
  let context = {
    detection: state.detection || null,
    plan: state.plan || null,
    paths: state.installedPaths || null,
    profile: state.selectedProfile || null
  };

  outputLine(flags, "PrepperGPT setup wizard");
  outputLine(flags, `Home: ${paths.root}`);
  if (previous && !boolFlag(flags.reset)) {
    outputLine(flags, "Found existing setup state; resuming completed work.");
  }

  try {
    context = await runStep({
      id: "detect",
      state,
      paths,
      flags,
      total,
      index: 1,
      context,
      action: async () => {
        const detection = deps.detectMachine ? await deps.detectMachine() : await detectMachine();
        state.detection = detection;
        state.hardware = summarizeDetection(detection);
        outputLine(flags, `  Hardware: ${state.hardware.ramGb} GB RAM, ${state.hardware.gpu}`);
        return { context: { detection }, step: { summary: state.hardware } };
      }
    });

    context = await runStep({
      id: "system-check",
      state,
      paths,
      flags,
      total,
      index: 2,
      context,
      action: async ({ detection }) => {
        const supportError = installSupportError(detection);
        if (supportError) {
          throw new Error(supportError);
        }
        const missing = [];
        if (!detection.tools?.docker) missing.push("Docker");
        if (!detection.tools?.dockerCompose) missing.push("Docker Compose");
        if (!detection.tools?.python3 && !detection.tools?.python) missing.push("Python 3");
        if (!detection.tools?.curl) missing.push("curl");
        if (missing.length) {
          throw new Error(`Missing required tools: ${missing.join(", ")}`);
        }
        return { step: { summary: "All required tools are available." } };
      }
    });

    context = await runStep({
      id: "profile",
      state,
      paths,
      flags,
      total,
      index: 3,
      context,
      action: async ({ detection }) => {
        const requested = await ask(
          flags,
          "Choose setup mode",
          flags.profile || "auto",
          ["auto", "balanced", "speed", "intelligence"]
        );
        const profile = normalizeWizardProfile(requested, detection);
        state.requestedProfile = requested;
        state.selectedProfile = profile;
        outputLine(flags, `  Selected: ${profile}`);
        return { context: { profile }, step: { summary: `Selected ${profile}.` } };
      }
    });

    context = await runStep({
      id: "plan",
      state,
      paths,
      flags,
      total,
      index: 4,
      context,
      action: async ({ detection, profile }) => {
        const plan = buildPlan(detection, profile);
        state.plan = plan;
        state.planSummary = summarizePlan(plan);
        const doctor = beginnerDoctorSummary(detection, plan);
        state.doctor = doctor;
        outputLine(flags, `  Default model: ${plan.defaultModel}`);
        if (plan.manualAssets.length) {
          outputLine(flags, "  Optional advanced models can be added later; the starter setup remains usable.");
        }
        return { context: { plan }, step: { summary: state.planSummary } };
      }
    });

    context = await runStep({
      id: "render",
      state,
      paths,
      flags,
      total,
      index: 5,
      context,
      action: async ({ plan, detection }) => {
        if (dryRun) {
          return { step: { summary: "Dry run: configuration not written." } };
        }
        const installedPaths = renderInstall(plan, detection, { home: paths.root });
        state.installedPaths = installedPaths;
        outputLine(flags, `  Wrote ${installedPaths.envFile}`);
        outputLine(flags, `  Wrote ${installedPaths.generatedCompose}`);
        return { context: { paths: installedPaths }, step: { summary: "Configuration written." } };
      }
    });

    context = await runStep({
      id: "bundle-whisper",
      state,
      paths,
      flags,
      total,
      index: 6,
      context,
      action: async ({ paths: installedPaths }) => {
        if (!shouldBundle) {
          return { step: { status: "skipped", summary: "Skipped by user flag." } };
        }
        if (dryRun) {
          return { step: { summary: "Dry run: bundle not downloaded." } };
        }
        const targetDir = installedPaths?.whisperHostDir || paths.whisperHostDir;
        let lastPercent = -1;
        const bundle = await ensureWhisperBundle(targetDir, {
          quiet: true,
          onProgress: (progress) => {
            if (progress.event === "start") {
              outputLine(flags, `  Downloading ${progress.file}`);
              appendLog(paths, `DOWNLOAD start ${progress.file}`, dryRun);
            }
            if (progress.event === "progress" && progress.totalBytes) {
              const percent = Math.floor((progress.downloadedBytes / progress.totalBytes) * 100);
              if (percent >= lastPercent + 25 || percent === 100) {
                lastPercent = percent;
                outputLine(flags, `  ${progress.file}: ${percent}%`);
              }
            }
          }
        });
        return { step: { summary: bundle.ready ? "Whisper Base is ready." : "Whisper Base is not ready." } };
      }
    });

    context = await runStep({
      id: "start",
      state,
      paths,
      flags,
      total,
      index: 7,
      context,
      action: async ({ paths: installedPaths }) => {
        if (!shouldStart) {
          outputLine(flags, `  Start skipped. Next command: npx --yes preppergpt start --home ${shellQuote(paths.root)}`);
          return { step: { status: "skipped", summary: "Start skipped." } };
        }
        if (dryRun) {
          outputLine(flags, "  Would start Docker Compose services.");
          return { step: { summary: "Dry run: services not started." } };
        }
        const runner = deps.runCompose || runCompose;
        runner(installedPaths || paths, ["up", "-d"]);
        return { step: { summary: "Docker Compose start requested." } };
      }
    });

    await runStep({
      id: "health",
      state,
      paths,
      flags,
      total,
      index: 8,
      context,
      action: async () => {
        if (!shouldStart) {
          return { step: { status: "skipped", summary: "Health check skipped." } };
        }
        if (dryRun) {
          return { step: { summary: "Dry run: health checks not run." } };
        }
        const fetcher = deps.fetchStatus || fetchStatus;
        const checks = await Promise.all([
          fetcher("http://127.0.0.1:8080/health"),
          fetcher("http://127.0.0.1:11434/api/tags")
        ]);
        state.health = checks;
        for (const check of checks) {
          outputLine(flags, `  ${check.ok ? "up" : "pending"} ${check.url} (${check.status})`);
        }
        return { step: { summary: checks } };
      }
    });

    const whisper = context.paths ? whisperBundleStatus(context.paths.whisperHostDir) : null;
    state.status = "complete";
    state.currentStep = null;
    state.nextAction = shouldStart
      ? "Open http://127.0.0.1:8080"
      : `Run npx --yes preppergpt start --home ${shellQuote(paths.root)} when ready.`;
    state.whisper = whisper ? { ready: whisper.ready, targetDir: whisper.targetDir } : null;
    saveState(paths, state, dryRun);
    outputLine(flags, "Setup wizard complete.");
    outputLine(flags, state.nextAction);
    return { state, paths };
  } catch (error) {
    if (boolFlag(flags.json)) {
      return { state, paths, error };
    }
    outputLine(flags, `Setup stopped: ${error?.message || error}`, process.stderr);
    outputLine(flags, `Next: ${state.nextAction || beginnerFixFor(error?.message || error)}`, process.stderr);
    throw error;
  }
}

export async function runWizardDoctor(flags = {}, deps = {}) {
  const detection = deps.detectMachine ? await deps.detectMachine() : await detectMachine();
  const profile = flags.profile && flags.profile !== "auto" ? normalizeProfile(flags.profile) : chooseAutoProfile(detection);
  const plan = buildPlan(detection, profile);
  return beginnerDoctorSummary(detection, plan);
}

export function printableWizardState(state) {
  return stateForJson(state);
}
