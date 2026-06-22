import fs from "node:fs";
import http from "node:http";
import { detectMachine } from "./lib/detect.mjs";
import { buildPlan, normalizeProfile } from "./lib/planner.mjs";
import { packageRoot, runtimePaths } from "./lib/paths.mjs";
import { renderInstall } from "./lib/render.mjs";
import { commandResult, parseArgs, readJson, shellQuote } from "./lib/util.mjs";

const VERSION = "0.1.0";

function usage() {
  return `PrepperGPT ${VERSION}

Usage:
  preppergpt detect [--json]
  preppergpt plan --profile balanced|intelligence|speed [--json]
  preppergpt install --profile balanced|intelligence|speed [--dry-run] [--home PATH]
  preppergpt start [--home PATH]
  preppergpt stop [--home PATH]
  preppergpt status [--home PATH] [--json]
  preppergpt doctor [--profile balanced|intelligence|speed] [--home PATH]
  preppergpt switch-profile --profile balanced|intelligence|speed [--home PATH]
  preppergpt version
`;
}

function printJson(value) {
  process.stdout.write(`${JSON.stringify(value, null, 2)}\n`);
}

function profileFrom(flags) {
  return normalizeProfile(flags.profile || flags.mode || "balanced");
}

function composeArgs(paths) {
  return ["compose", "--env-file", paths.envFile, "-f", `${packageRoot}/compose/preppergpt.yaml`, "-f", paths.generatedCompose];
}

function runCompose(paths, args) {
  const result = commandResult("docker", [...composeArgs(paths), ...args], {
    timeoutMs: 120000,
    stdio: ["ignore", "inherit", "inherit"]
  });
  if (!result.ok) {
    throw new Error(`docker compose ${args.join(" ")} failed`);
  }
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

function printPlan(plan) {
  console.log(`Profile: ${plan.profileLabel}`);
  console.log(`Default model: ${plan.defaultModel}`);
  console.log(`Routes: ${plan.routeIds.join(", ")}`);
  console.log(`Context: default ${plan.estimates.defaultContextTokens}, max ${plan.estimates.maxContextTokens}`);
  console.log(`TPS estimate: default ${plan.estimates.defaultTpsEstimate}; best ${plan.estimates.bestTpsEstimate}`);
  if (plan.manualAssets.length) {
    console.log("\nManual or external assets:");
    for (const asset of plan.manualAssets) {
      console.log(`  ${asset.id}: ${asset.reason}`);
    }
  }
  if (plan.warnings.length) {
    console.log("\nWarnings:");
    for (const warning of plan.warnings) {
      console.log(`  ${warning}`);
    }
  }
}

async function commandDetect(flags) {
  const detection = await detectMachine();
  if (flags.json) {
    printJson(detection);
    return;
  }
  console.log(`Host: ${detection.hostname} (${detection.platform}/${detection.arch})`);
  console.log(`CPU: ${detection.cpu.cores} cores, ${detection.cpu.model}`);
  console.log(`RAM: ${detection.memory.totalGb} GB total, ${detection.memory.freeGb} GB free`);
  const bestDisk = detection.disks[0];
  console.log(`Disk: ${bestDisk ? `${bestDisk.freeGb.toFixed(1)} GB free at ${bestDisk.mount}` : "not detected"}`);
  if (detection.gpus.length) {
    for (const gpu of detection.gpus) {
      console.log(`GPU ${gpu.index}: ${gpu.name}, ${gpu.totalVramGb} GB VRAM, ${gpu.freeVramGb} GB free`);
    }
  } else {
    console.log("GPU: no NVIDIA GPU detected");
  }
  const missing = Object.entries(detection.tools).filter(([, present]) => !present).map(([tool]) => tool);
  console.log(`Tools: ${missing.length ? `missing ${missing.join(", ")}` : "all required tools present"}`);
}

async function commandPlan(flags) {
  const detection = await detectMachine({ skipPorts: Boolean(flags.no_ports) });
  const plan = buildPlan(detection, profileFrom(flags));
  if (flags.json) {
    printJson(plan);
    return;
  }
  printPlan(plan);
}

async function commandInstall(flags) {
  const home = flags.home;
  const detection = await detectMachine();
  const plan = buildPlan(detection, profileFrom(flags));
  if (flags.dry_run) {
    printPlan(plan);
    console.log("\nDry run only. No files written.");
    return;
  }
  const paths = renderInstall(plan, detection, { home });
  console.log(`Wrote ${paths.envFile}`);
  console.log(`Wrote ${paths.generatedCompose}`);
  console.log(`Wrote ${paths.modelPlan}`);
  console.log("\nNext:");
  console.log(`  preppergpt start --home ${shellQuote(paths.root)}`);
  console.log("  Open http://127.0.0.1:8080");
}

async function commandSwitchProfile(flags) {
  const paths = runtimePaths(flags.home);
  const detection = await detectMachine();
  const plan = buildPlan(detection, profileFrom(flags));
  renderInstall(plan, detection, { home: paths.root });
  console.log(`Switched PrepperGPT to ${plan.profile}.`);
}

async function commandStart(flags) {
  const paths = runtimePaths(flags.home);
  if (!fs.existsSync(paths.envFile) || !fs.existsSync(paths.generatedCompose)) {
    throw new Error(`PrepperGPT is not installed at ${paths.root}. Run preppergpt install first.`);
  }
  runCompose(paths, ["up", "-d"]);
  console.log("PrepperGPT start requested.");
  console.log("Open http://127.0.0.1:8080");
}

async function commandStop(flags) {
  const paths = runtimePaths(flags.home);
  runCompose(paths, ["stop"]);
}

async function commandStatus(flags) {
  const paths = runtimePaths(flags.home);
  const checks = await Promise.all([
    fetchStatus("http://127.0.0.1:8080/health"),
    fetchStatus("http://127.0.0.1:11434/api/tags"),
    fetchStatus("http://127.0.0.1:18041/health"),
    fetchStatus("http://127.0.0.1:18042/health"),
    fetchStatus("http://127.0.0.1:18043/health"),
    fetchStatus("http://127.0.0.1:18044/health"),
    fetchStatus("http://127.0.0.1:18080/search?q=test&format=json")
  ]);
  let plan = null;
  if (fs.existsSync(paths.modelPlan)) {
    plan = readJson(paths.modelPlan);
  }
  const status = { home: paths.root, url: "http://127.0.0.1:8080", plan, checks };
  if (flags.json) {
    printJson(status);
    return;
  }
  console.log(`PrepperGPT home: ${paths.root}`);
  console.log(`OpenWebUI URL: ${status.url}`);
  if (plan) {
    console.log(`Profile: ${plan.profile}`);
    console.log(`Default model: ${plan.defaultModel}`);
    console.log(`Context limit estimate: ${plan.estimates.maxContextTokens}`);
    console.log(`TPS estimate: ${plan.estimates.bestTpsEstimate}`);
  }
  for (const check of checks) {
    console.log(`${check.ok ? "up  " : "down"} ${check.url} (${check.status})`);
  }
}

async function commandDoctor(flags) {
  const detection = await detectMachine();
  const plan = buildPlan(detection, profileFrom(flags));
  printPlan(plan);
  console.log("\nDoctor:");
  const requiredTools = ["docker", "dockerCompose", "curl", "python3"];
  for (const tool of requiredTools) {
    console.log(`  ${tool}: ${detection.tools[tool] ? "ok" : "missing"}`);
  }
  for (const [port, entry] of Object.entries(detection.ports)) {
    if (!entry.free) {
      console.log(`  port ${port}: occupied`);
    }
  }
}

export async function runCli(argv) {
  const { flags, positional } = parseArgs(argv);
  const command = positional[0] || (flags.help ? "help" : "");
  if (!command || command === "help" || flags.help) {
    console.log(usage());
    return;
  }
  if (command === "version" || command === "--version") {
    console.log(VERSION);
    return;
  }
  if (command === "detect") return commandDetect(flags);
  if (command === "plan") return commandPlan(flags);
  if (command === "install") return commandInstall(flags);
  if (command === "start") return commandStart(flags);
  if (command === "stop") return commandStop(flags);
  if (command === "status") return commandStatus(flags);
  if (command === "doctor") return commandDoctor(flags);
  if (command === "switch-profile") return commandSwitchProfile(flags);
  throw new Error(`Unknown command: ${command}\n\n${usage()}`);
}
