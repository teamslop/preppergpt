import { packagedPath } from "./paths.mjs";
import { readJson, unique } from "./util.mjs";

export function loadCatalog() {
  return readJson(packagedPath("profiles", "models.json"));
}

export function normalizeProfile(profile) {
  const value = String(profile || "balanced").toLowerCase();
  if (["intelligence", "max-intelligence", "max_intelligence", "smart", "quality"].includes(value)) {
    return "intelligence";
  }
  if (["speed", "max-speed", "max_speed", "fast"].includes(value)) {
    return "speed";
  }
  if (["balanced", "balance", "middle", "middle-ground", "middle_ground"].includes(value)) {
    return "balanced";
  }
  throw new Error(`Unknown profile: ${profile}`);
}

function bestDisk(detection) {
  return detection.disks?.[0] || { freeGb: 0, isNvme: false, path: "" };
}

function bestGpu(detection) {
  return [...(detection.gpus || [])].sort((a, b) => b.usableVramGb - a.usableVramGb)[0] || null;
}

function requirementFailures(model, detection) {
  const requires = model.requires || {};
  const disk = bestDisk(detection);
  const gpu = bestGpu(detection);
  const failures = [];
  if (requires.platforms && !requires.platforms.includes(detection.platform)) {
    failures.push(`requires platform ${requires.platforms.join(", ")}`);
  }
  if (requires.minRamGb && detection.memory.totalGb < requires.minRamGb) {
    failures.push(`requires ${requires.minRamGb} GB RAM`);
  }
  if (requires.diskGb && disk.freeGb < requires.diskGb) {
    failures.push(`requires ${requires.diskGb} GB free disk`);
  }
  if (requires.nvme && disk.freeGb >= (requires.diskGb || 0) && !disk.isNvme) {
    failures.push("strongly prefers NVMe for acceptable load time");
  }
  if (requires.gpu && !gpu) {
    failures.push("requires NVIDIA GPU");
  }
  if (requires.minVramGb && (!gpu || gpu.usableVramGb < requires.minVramGb)) {
    failures.push(`requires about ${requires.minVramGb} GB usable VRAM`);
  }
  return failures;
}

function chooseFirst(candidates, models, detection) {
  const skipped = [];
  for (const id of candidates) {
    const model = models.get(id);
    if (!model) {
      skipped.push({ id, reasons: ["not in catalog"] });
      continue;
    }
    const failures = requirementFailures(model, detection);
    if (failures.length === 0 || model.source?.type === "manual" || model.source?.type === "external") {
      return { model, skipped };
    }
    skipped.push({ id, reasons: failures });
  }
  return { model: null, skipped };
}

export function buildPlan(detection, requestedProfile = "balanced", catalog = loadCatalog()) {
  const profile = normalizeProfile(requestedProfile);
  const models = new Map(catalog.models.map((model) => [model.id, model]));
  const priorities = catalog.profiles[profile];
  const selected = {};
  const skipped = {};

  for (const [role, candidates] of Object.entries(priorities.roles)) {
    const choice = chooseFirst(candidates, models, detection);
    if (choice.model) {
      selected[role] = {
        ...choice.model,
        requirementWarnings: requirementFailures(choice.model, detection),
        needsManualAssets: ["manual", "external"].includes(choice.model.source?.type)
      };
    }
    if (choice.skipped.length) {
      skipped[role] = choice.skipped;
    }
  }

  const routeIds = unique([
    priorities.defaultModel,
    selected.chat?.id,
    selected.fast?.id,
    selected.reasoning?.id,
    selected.coding?.id,
    selected.research?.id,
    selected.agent?.id,
    selected.vision?.id,
    selected.image?.id,
    selected.stt?.id
  ]);

  const manualAssets = Object.values(selected)
    .filter((model) => model.needsManualAssets)
    .map((model) => ({
      id: model.id,
      source: model.source,
      reason: model.source?.description || "manual or external source"
    }));

  const warnings = [];
  const missingTools = Object.entries(detection.tools || {})
    .filter(([tool, present]) => ["docker", "dockerCompose", "curl", "python3"].includes(tool) && !present)
    .map(([tool]) => tool);
  if (missingTools.length) {
    warnings.push(`Missing required tools: ${missingTools.join(", ")}`);
  }
  const occupiedPorts = Object.values(detection.ports || {})
    .filter((entry) => !entry.free)
    .map((entry) => entry.port);
  if (occupiedPorts.length) {
    warnings.push(`Ports already in use: ${occupiedPorts.join(", ")}`);
  }
  if (!detection.gpus?.length) {
    warnings.push("No NVIDIA GPU detected; CPU fallback will be much slower.");
  }
  if (manualAssets.length) {
    warnings.push("Some selected high-quality routes need manual model files or already-running external endpoints.");
  }

  return {
    generatedAt: new Date().toISOString(),
    profile,
    profileLabel: priorities.label,
    defaultModel: priorities.defaultModel,
    routeIds,
    selected,
    skipped,
    manualAssets,
    estimates: estimatePlan(profile, selected),
    env: {
      PREPPERGPT_PROFILE: profile,
      PREPPERGPT_DEFAULT_MODEL: priorities.defaultModel,
      PREPPERGPT_MODEL_ORDER_LIST: JSON.stringify(routeIds)
    },
    warnings
  };
}

function estimatePlan(profile, selected) {
  const chat = selected.chat || selected.fast || selected.reasoning;
  const fast = selected.fast || chat;
  const contextTokens = Math.max(
    ...Object.values(selected)
      .map((model) => model.contextTokens || 0)
      .filter(Boolean),
    0
  );
  return {
    defaultContextTokens: chat?.contextTokens || 8192,
    maxContextTokens: contextTokens || 8192,
    defaultTpsEstimate: chat?.tpsEstimate || "unknown until benchmarked",
    bestTpsEstimate: fast?.tpsEstimate || "unknown until benchmarked",
    note:
      profile === "intelligence"
        ? "Max intelligence favors quality and context over latency."
        : profile === "speed"
          ? "Max speed favors low-latency routes over largest weights."
          : "Middle ground uses the local auto-router and keeps specialist routes additive."
  };
}
