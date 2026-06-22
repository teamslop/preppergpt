import fs from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";

export function commandResult(command, args = [], options = {}) {
  const result = spawnSync(command, args, {
    encoding: "utf8",
    timeout: options.timeoutMs || 15000,
    shell: false,
    stdio: ["ignore", "pipe", "pipe"],
    ...options
  });
  return {
    ok: result.status === 0,
    status: result.status,
    stdout: result.stdout || "",
    stderr: result.stderr || "",
    error: result.error
  };
}

export function commandExists(command) {
  return commandResult("sh", ["-lc", `command -v ${shellQuote(command)}`], { timeoutMs: 3000 }).ok;
}

export function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

export function writeJson(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`);
}

export function writeText(file, value, mode) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, value);
  if (mode) {
    fs.chmodSync(file, mode);
  }
}

export function shellQuote(value) {
  return `'${String(value).replaceAll("'", "'\\''")}'`;
}

export function envQuote(value) {
  const text = String(value ?? "");
  if (/^[A-Za-z0-9_./:@,+-]*$/.test(text)) {
    return text;
  }
  return JSON.stringify(text);
}

export function parseArgs(argv) {
  const flags = {};
  const positional = [];
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (!arg.startsWith("--")) {
      positional.push(arg);
      continue;
    }
    const [rawKey, inlineValue] = arg.slice(2).split(/=(.*)/s, 2);
    const key = rawKey.replaceAll("-", "_");
    if (inlineValue !== undefined) {
      flags[key] = inlineValue;
    } else if (argv[index + 1] && !argv[index + 1].startsWith("--")) {
      flags[key] = argv[index + 1];
      index += 1;
    } else {
      flags[key] = true;
    }
  }
  return { flags, positional };
}

export function gb(bytes) {
  return Math.round((bytes / 1024 ** 3) * 10) / 10;
}

export function unique(values) {
  return [...new Set(values.filter(Boolean))];
}
