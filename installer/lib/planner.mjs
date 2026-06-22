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

function detectedPlatformKind(detection) {
  if (detection.platformKind) {
    return detection.platformKind;
  }
  if (detection.platform === "win32") {
    return "windows-native";
  }
  if (detection.platform === "darwin") {
    return "macos";
  }
  return detection.platform || "unknown";
}

function bestGpu(detection, vendors = null) {
  const allowed = vendors ? new Set(vendors) : null;
  return [...(detection.gpus || [])]
    .filter((gpu) => !allowed || allowed.has(gpu.vendor))
    .sort((a, b) => (b.usableVramGb || 0) - (a.usableVramGb || 0))[0] || null;
}

function gpuVendorLabel(vendors) {
  if (!vendors?.length) {
    return "supported";
  }
  return vendors.map((vendor) => (vendor === "nvidia" ? "NVIDIA" : vendor === "amd" ? "AMD" : vendor)).join("/");
}

function hasRocmRuntime(detection) {
  return Boolean(detection.tools?.rocmSmi || detection.tools?.rocminfo);
}

export function installSupportError(detection) {
  if (detectedPlatformKind(detection) === "windows-native") {
    return "Native Windows install is not supported yet. Install PrepperGPT inside WSL2 so Docker, Linux paths, and local model services use the supported Linux runtime.";
  }
  return null;
}

function requirementFailures(model, detection) {
  const requires = model.requires || {};
  const disk = bestDisk(detection);
  const platformKind = detectedPlatformKind(detection);
  const gpuVendors = requires.gpuVendors || null;
  const gpu = bestGpu(detection, gpuVendors);
  const failures = [];
  if (requires.platforms && !requires.platforms.includes(detection.platform)) {
    failures.push(`requires platform ${requires.platforms.join(", ")}`);
  }
  if (requires.platformKinds && !requires.platformKinds.includes(platformKind)) {
    failures.push(`requires platform kind ${requires.platformKinds.join(", ")}`);
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
  if (requires.gpuVendors && detection.gpus?.length && !gpu) {
    failures.push(`requires ${gpuVendorLabel(requires.gpuVendors)} GPU`);
  }
  if (requires.gpu && !gpu) {
    failures.push(`requires ${gpuVendorLabel(requires.gpuVendors)} GPU`);
  }
  if (requires.minVramGb && (!gpu || gpu.usableVramGb < requires.minVramGb)) {
    failures.push(`requires ${gpuVendorLabel(requires.gpuVendors)} GPU with about ${requires.minVramGb} GB usable VRAM`);
  }
  if (requires.requiresRocm && gpu?.vendor === "amd") {
    if (platformKind !== "linux") {
      failures.push("requires a Linux ROCm host for AMD GPU acceleration");
    }
    if (gpu.runtime !== "rocm" || !hasRocmRuntime(detection)) {
      failures.push("requires ROCm runtime tools for AMD GPU acceleration");
    }
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
    const canUseExternalFallback =
      ["manual", "external"].includes(model.source?.type) && !model.source?.requiresHardwareFit;
    if (failures.length === 0 || canUseExternalFallback) {
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

  const defaultModel = selected.chat?.id || priorities.defaultModel;
  const routeIds = unique([
    defaultModel,
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
  const installError = installSupportError(detection);
  if (installError) {
    warnings.push(installError);
  }
  const missingTools = Object.entries(detection.tools || {})
    .filter(([tool, present]) => ["docker", "dockerCompose", "curl"].includes(tool) && !present)
    .map(([tool]) => tool);
  if (!detection.tools?.python3 && !detection.tools?.python) {
    missingTools.push("python3 or python");
  }
  if (missingTools.length) {
    warnings.push(`Missing required tools: ${missingTools.join(", ")}`);
  }
  const occupiedPorts = Object.values(detection.ports || {})
    .filter((entry) => !entry.free)
    .map((entry) => entry.port);
  if (occupiedPorts.length) {
    warnings.push(`Ports already in use: ${occupiedPorts.join(", ")}`);
  }
  const acceleratedGpu = (detection.gpus || []).find(
    (gpu) => gpu.vendor === "nvidia" || (gpu.vendor === "amd" && gpu.runtime === "rocm" && detectedPlatformKind(detection) === "linux")
  );
  if (!acceleratedGpu) {
    warnings.push("No supported GPU acceleration detected; CPU fallback will be much slower.");
  }
  const amdWithoutRocm = (detection.gpus || []).some((gpu) => gpu.vendor === "amd" && gpu.runtime !== "rocm");
  if (amdWithoutRocm) {
    warnings.push("AMD GPU detected without ROCm; install ROCm on Linux to enable AMD acceleration.");
  }
  if ((detection.gpus || []).some((gpu) => gpu.vendor === "amd") && detectedPlatformKind(detection) === "wsl2") {
    warnings.push("AMD GPU acceleration is supported on Linux ROCm hosts; WSL2 installs will use CPU fallback unless an external AMD endpoint is provided.");
  }
  if (manualAssets.length) {
    warnings.push("Some selected high-quality routes need manual model files or already-running external endpoints.");
  }

  return {
    generatedAt: new Date().toISOString(),
    profile,
    profileLabel: priorities.label,
    defaultModel,
    routeIds,
    selected,
    skipped,
    manualAssets,
    estimates: estimatePlan(profile, selected),
    env: {
      PREPPERGPT_PROFILE: profile,
      PREPPERGPT_DEFAULT_MODEL: defaultModel,
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
