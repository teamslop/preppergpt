import fs from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { commandExists, commandResult, gb } from "./util.mjs";

const DEFAULT_PORTS = [8080, 11434, 11438, 11441, 18041, 18042, 18043, 18044, 18045, 18080, 8188, 8888, 9998];

function readFileMaybe(file) {
  try {
    return fs.readFileSync(file, "utf8");
  } catch {
    return "";
  }
}

export function detectPlatformKind() {
  if (process.platform === "win32") {
    return "windows-native";
  }
  if (process.platform === "darwin") {
    return "macos";
  }
  if (process.platform !== "linux") {
    return "unknown";
  }
  const release = `${readFileMaybe("/proc/sys/kernel/osrelease")}\n${readFileMaybe("/proc/version")}`.toLowerCase();
  if (process.env.WSL_DISTRO_NAME || process.env.WSL_INTEROP || release.includes("microsoft") || release.includes("wsl")) {
    return "wsl2";
  }
  return "linux";
}

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

function usableVram(totalVramGb) {
  return Math.round(totalVramGb * 0.82 * 10) / 10;
}

function normalizeGb(value) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.round(number * 10) / 10 : null;
}

function bytesToGb(value) {
  const number = Number(value);
  return Number.isFinite(number) ? normalizeGb(number / 1024 ** 3) : null;
}

function memoryToGb(value, fallbackUnit = "bytes") {
  if (value === null || value === undefined) {
    return null;
  }
  const text = String(value).trim();
  const matches = [...text.matchAll(/(\d+(?:\.\d+)?)/g)];
  const number = Number(matches.at(-1)?.[1]);
  if (!Number.isFinite(number)) {
    return null;
  }
  const lower = text.toLowerCase();
  if (/(gib|gb)/.test(lower)) {
    return normalizeGb(number);
  }
  if (/(mib|mb)/.test(lower)) {
    return normalizeGb(number / 1024);
  }
  if (/(kib|kb)/.test(lower)) {
    return normalizeGb(number / 1024 / 1024);
  }
  if (/\(b\)|bytes?/.test(lower) || number > 1024 ** 3) {
    return bytesToGb(number);
  }
  if (fallbackUnit === "mib" || number > 1024) {
    return normalizeGb(number / 1024);
  }
  if (fallbackUnit === "bytes") {
    return bytesToGb(number);
  }
  return normalizeGb(number);
}

function bestMatchingKey(record, patterns) {
  return Object.keys(record).find((key) => patterns.some((pattern) => pattern.test(key)));
}

function detectNvidiaGpus() {
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
        runtime: "cuda",
        name,
        totalVramGb: normalizeGb(Number(totalMiB) / 1024),
        freeVramGb: normalizeGb(Number(freeMiB) / 1024),
        usableVramGb: usableVram(Number(totalMiB) / 1024),
        driver
      };
    })
    .filter((gpu) => gpu.name && Number.isFinite(gpu.totalVramGb));
}

function detectAmdRocmSmiGpus() {
  if (!commandExists("rocm-smi")) {
    return [];
  }
  const jsonResult = commandResult("rocm-smi", [
    "--showproductname",
    "--showmeminfo",
    "vram",
    "--showdriverversion",
    "--json"
  ]);
  if (jsonResult.ok) {
    try {
      const parsed = JSON.parse(jsonResult.stdout);
      return Object.entries(parsed)
        .filter(([id, record]) => /^card\d+/i.test(id) && record && typeof record === "object")
        .map(([id, record], index) => {
          const totalKey = bestMatchingKey(record, [/vram.*total/i, /total.*memory/i]);
          const usedKey = bestMatchingKey(record, [/vram.*used/i, /used.*memory/i]);
          const nameKey = bestMatchingKey(record, [/product.*name/i, /card.*series/i, /marketing.*name/i]);
          const driverKey = bestMatchingKey(record, [/driver/i]);
          const totalVramGb = memoryToGb(record[totalKey]);
          const usedVramGb = memoryToGb(record[usedKey]) || 0;
          const freeVramGb = totalVramGb === null ? null : normalizeGb(Math.max(totalVramGb - usedVramGb, 0));
          return {
            index,
            vendor: "amd",
            runtime: "rocm",
            name: String(record[nameKey] || id),
            totalVramGb,
            freeVramGb,
            usableVramGb: totalVramGb === null ? null : usableVram(totalVramGb),
            driver: String(record[driverKey] || "")
          };
        })
        .filter((gpu) => gpu.name);
    } catch {
      // Fall through to text parsing.
    }
  }

  const textResult = commandResult("rocm-smi", ["--showproductname", "--showmeminfo", "vram", "--showdriverversion"]);
  if (!textResult.ok) {
    return [];
  }
  const cards = new Map();
  for (const line of textResult.stdout.split(/\n/)) {
    const match = line.match(/(card\d+)\s*[:\t ]+(.*)$/i);
    if (!match) {
      continue;
    }
    const [, id, value] = match;
    const record = cards.get(id) || {};
    if (/product|series|marketing/i.test(value)) {
      record.name = value.split(/[:=]/).at(-1)?.trim() || record.name;
    }
    if (/total.*vram|vram.*total/i.test(value)) {
      record.totalVramGb = memoryToGb(value);
    }
    if (/used.*vram|vram.*used/i.test(value)) {
      record.usedVramGb = memoryToGb(value);
    }
    if (/driver/i.test(value)) {
      record.driver = value.split(/[:=]/).at(-1)?.trim();
    }
    cards.set(id, record);
  }
  return [...cards.entries()].map(([id, record], index) => {
    const totalVramGb = record.totalVramGb ?? null;
    const freeVramGb =
      totalVramGb === null ? null : normalizeGb(Math.max(totalVramGb - (record.usedVramGb || 0), 0));
    return {
      index,
      vendor: "amd",
      runtime: "rocm",
      name: record.name || id,
      totalVramGb,
      freeVramGb,
      usableVramGb: totalVramGb === null ? null : usableVram(totalVramGb),
      driver: record.driver || ""
    };
  });
}

function detectAmdRocinfoGpus() {
  if (!commandExists("rocminfo")) {
    return [];
  }
  const result = commandResult("rocminfo", [], { timeoutMs: 8000 });
  if (!result.ok) {
    return [];
  }
  const names = [];
  for (const line of result.stdout.split(/\n/)) {
    const match = line.match(/^\s*(?:Marketing Name|Name):\s*(.+)$/);
    if (match && /amd|radeon|instinct|gfx/i.test(match[1])) {
      names.push(match[1].trim());
    }
  }
  return [...new Set(names)].map((name, index) => ({
    index,
    vendor: "amd",
    runtime: "rocm",
    name,
    totalVramGb: null,
    freeVramGb: null,
    usableVramGb: null,
    driver: ""
  }));
}

function detectAmdPciGpus() {
  if (!commandExists("lspci")) {
    return [];
  }
  const result = commandResult("lspci", ["-mm"], { timeoutMs: 5000 });
  if (!result.ok) {
    return [];
  }
  return result.stdout
    .split(/\n/)
    .filter((line) => /(VGA compatible controller|3D controller|Display controller)/i.test(line) && /AMD|ATI|Radeon/i.test(line))
    .map((line, index) => ({
      index,
      vendor: "amd",
      runtime: "none",
      name: line.replace(/^\S+\s+/, "").replaceAll('"', "").trim() || "AMD GPU",
      totalVramGb: null,
      freeVramGb: null,
      usableVramGb: null,
      driver: ""
    }));
}

function dedupeGpus(gpus) {
  const seen = new Set();
  return gpus.filter((gpu) => {
    const key = `${gpu.vendor}:${gpu.name}:${gpu.totalVramGb ?? "unknown"}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function detectGpus() {
  const nvidia = detectNvidiaGpus();
  const amdRocm = detectAmdRocmSmiGpus();
  const amdFallback = amdRocm.length ? [] : detectAmdRocinfoGpus();
  const amdPci = amdRocm.length || amdFallback.length ? [] : detectAmdPciGpus();
  return dedupeGpus([...nvidia, ...amdRocm, ...amdFallback, ...amdPci]);
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
  const platformKind = detectPlatformKind();
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
    python: commandExists("python"),
    git: commandExists("git"),
    nvidiaSmi: commandExists("nvidia-smi"),
    rocmSmi: commandExists("rocm-smi"),
    rocminfo: commandExists("rocminfo")
  };
  return {
    generatedAt: new Date().toISOString(),
    platform: process.platform,
    platformKind,
    isWsl2: platformKind === "wsl2",
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
