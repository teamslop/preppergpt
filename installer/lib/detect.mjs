import fs from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { commandExists, commandResult, gb } from "./util.mjs";

const DEFAULT_PORTS = [8080, 11434, 11438, 11441, 18041, 18042, 18043, 18044, 18045, 18080, 8188, 8888, 9998];

function parseDf(target) {
  const result = commandResult("df", ["-Pk", target], { timeoutMs: 5000 });
  if (!result.ok) {
    return null;
  }
  const lines = result.stdout.trim().split(/\n/);
  const fields = lines.at(-1)?.trim().split(/\s+/);
  if (!fields || fields.length < 6) {
    return null;
  }
  return {
    path: target,
    filesystem: fields[0],
    sizeGb: Number(fields[1]) / 1024 / 1024,
    usedGb: Number(fields[2]) / 1024 / 1024,
    freeGb: Number(fields[3]) / 1024 / 1024,
    mount: fields[5],
    isNvme: fields[0].includes("nvme") || fields[5].toLowerCase().includes("nvme")
  };
}

function candidateDiskPaths() {
  const candidates = [
    process.env.PREPPERGPT_MODELS_DIR,
    process.env.PREPPERGPT_DATA_DIR,
    path.join(os.homedir(), ".preppergpt"),
    "/models",
    "/data",
    "/mnt",
    "/media",
    process.cwd()
  ].filter(Boolean);
  return [...new Set(candidates)].filter((candidate) => {
    try {
      return fs.existsSync(candidate) || fs.existsSync(path.dirname(candidate));
    } catch {
      return false;
    }
  });
}

function detectGpus() {
  if (!commandExists("nvidia-smi")) {
    return [];
  }
  const result = commandResult("nvidia-smi", [
    "--query-gpu=name,memory.total,memory.free,driver_version",
    "--format=csv,noheader,nounits"
  ]);
  if (!result.ok) {
    return [];
  }
  return result.stdout
    .trim()
    .split(/\n/)
    .map((line, index) => {
      const [name, totalMiB, freeMiB, driver] = line.split(",").map((part) => part.trim());
      return {
        index,
        vendor: "nvidia",
        name,
        totalVramGb: Math.round((Number(totalMiB) / 1024) * 10) / 10,
        freeVramGb: Math.round((Number(freeMiB) / 1024) * 10) / 10,
        usableVramGb: Math.round((Number(totalMiB) / 1024) * 0.82 * 10) / 10,
        driver
      };
    })
    .filter((gpu) => gpu.name && Number.isFinite(gpu.totalVramGb));
}

async function portFree(port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once("error", () => resolve(false));
    server.once("listening", () => {
      server.close(() => resolve(true));
    });
    server.listen(port, "127.0.0.1");
  });
}

async function detectPorts(ports = DEFAULT_PORTS) {
  const entries = await Promise.all(ports.map(async (port) => [port, await portFree(port)]));
  return Object.fromEntries(entries.map(([port, free]) => [String(port), { port, free }]));
}

export async function detectMachine(options = {}) {
  const disks = candidateDiskPaths()
    .map(parseDf)
    .filter(Boolean)
    .sort((a, b) => b.freeGb - a.freeGb);
  const gpus = detectGpus();
  const tools = {
    docker: commandExists("docker"),
    dockerCompose: commandResult("docker", ["compose", "version"], { timeoutMs: 5000 }).ok,
    tmux: commandExists("tmux"),
    curl: commandExists("curl"),
    python3: commandExists("python3"),
    git: commandExists("git"),
    nvidiaSmi: commandExists("nvidia-smi")
  };
  return {
    generatedAt: new Date().toISOString(),
    platform: process.platform,
    arch: process.arch,
    hostname: os.hostname(),
    cpu: {
      model: os.cpus()[0]?.model || "unknown",
      cores: os.cpus().length
    },
    memory: {
      totalGb: gb(os.totalmem()),
      freeGb: gb(os.freemem())
    },
    disks,
    gpus,
    tools,
    ports: options.skipPorts ? {} : await detectPorts(options.ports || DEFAULT_PORTS)
  };
}
