import fs from "node:fs";
import path from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { readJson, writeJson } from "./util.mjs";

export const WHISPER_BUNDLE = {
  id: "whisper-base",
  name: "Whisper Base STT Bundle",
  repo: "Systran/faster-whisper-base",
  revision: "main",
  license: "MIT",
  modelPathInContainer: "/models/whisper/base",
  files: ["config.json", "model.bin", "tokenizer.json", "vocabulary.txt", "README.md"],
  description: "CTranslate2 faster-whisper conversion of openai/whisper-base for local OpenWebUI STT."
};

function parseEnvFile(file) {
  if (!fs.existsSync(file)) {
    return {};
  }
  const entries = {};
  for (const line of fs.readFileSync(file, "utf8").split(/\r?\n/)) {
    if (!line || line.trim().startsWith("#") || !line.includes("=")) {
      continue;
    }
    const [key, ...valueParts] = line.split("=");
    let value = valueParts.join("=");
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    entries[key] = value;
  }
  return entries;
}

export function modelDirs(paths) {
  const env = parseEnvFile(paths.envFile);
  const modelsDir = process.env.PREPPERGPT_MODELS_DIR || env.PREPPERGPT_MODELS_DIR || path.join(paths.dataDir, "models");
  const whisperHostDir = path.join(modelsDir, "whisper", "base");
  return { modelsDir, whisperHostDir };
}

export function whisperBundleStatus(targetDir) {
  const files = WHISPER_BUNDLE.files.map((file) => path.join(targetDir, file));
  const missing = files.filter((file) => !fs.existsSync(file));
  let manifest = null;
  const manifestPath = path.join(targetDir, "preppergpt-bundle.json");
  if (fs.existsSync(manifestPath)) {
    try {
      manifest = readJson(manifestPath);
    } catch {
      manifest = null;
    }
  }
  return {
    id: WHISPER_BUNDLE.id,
    targetDir,
    ready: missing.length === 0,
    missing,
    manifest
  };
}

async function downloadFile(url, targetFile, options = {}) {
  const response = await fetch(url, {
    headers: {
      "User-Agent": "preppergpt/0.1"
    },
    redirect: "follow"
  });
  if (!response.ok || !response.body) {
    throw new Error(`Failed to download ${url}: HTTP ${response.status}`);
  }
  fs.mkdirSync(path.dirname(targetFile), { recursive: true });
  const tmp = `${targetFile}.tmp-${process.pid}`;
  const totalBytes = Number(response.headers.get("content-length")) || null;
  let downloadedBytes = 0;
  const stream = Readable.fromWeb(response.body);
  stream.on("data", (chunk) => {
    downloadedBytes += chunk.length;
    options.onProgress?.({
      event: "progress",
      url,
      targetFile,
      downloadedBytes,
      totalBytes
    });
  });
  await pipeline(stream, fs.createWriteStream(tmp));
  fs.renameSync(tmp, targetFile);
  options.onProgress?.({
    event: "done",
    url,
    targetFile,
    downloadedBytes,
    totalBytes
  });
}

export async function ensureWhisperBundle(targetDir, options = {}) {
  const status = whisperBundleStatus(targetDir);
  if (status.ready && !options.force) {
    return { ...status, changed: false };
  }
  fs.mkdirSync(targetDir, { recursive: true });
  if (options.dryRun) {
    return { ...status, changed: false, dryRun: true };
  }
  for (const file of WHISPER_BUNDLE.files) {
    const targetFile = path.join(targetDir, file);
    if (fs.existsSync(targetFile) && !options.force) {
      options.onProgress?.({
        event: "skip",
        file,
        targetFile,
        bundle: WHISPER_BUNDLE.id
      });
      continue;
    }
    const url = `https://huggingface.co/${WHISPER_BUNDLE.repo}/resolve/${WHISPER_BUNDLE.revision}/${file}`;
    if (!options.quiet) {
      console.log(`Downloading ${WHISPER_BUNDLE.repo}/${file}`);
    }
    options.onProgress?.({
      event: "start",
      file,
      targetFile,
      bundle: WHISPER_BUNDLE.id
    });
    await downloadFile(url, targetFile, {
      onProgress: (progress) => options.onProgress?.({ ...progress, file, bundle: WHISPER_BUNDLE.id })
    });
  }
  writeJson(path.join(targetDir, "preppergpt-bundle.json"), {
    ...WHISPER_BUNDLE,
    installedAt: new Date().toISOString(),
    source: `https://huggingface.co/${WHISPER_BUNDLE.repo}`
  });
  return { ...whisperBundleStatus(targetDir), changed: true };
}
