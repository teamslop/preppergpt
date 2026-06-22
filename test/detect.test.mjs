import assert from "node:assert/strict";
import test from "node:test";
import { amdPciGpuFromLspciLine, parseLspciMachineLine } from "../installer/lib/detect.mjs";

test("parseLspciMachineLine handles quoted lspci -mm fields", () => {
  const fields = parseLspciMachineLine(
    '05:00.0 "VGA compatible controller" "NVIDIA Corporation" "Device 2c02" -ra1 -p00 "Micro-Star International Co., Ltd. [MSI]" "Device 5310"'
  );
  assert.deepEqual(fields.slice(0, 4), ["05:00.0", "VGA compatible controller", "NVIDIA Corporation", "Device 2c02"]);
});

test("AMD PCI fallback does not match ATI substring inside International", () => {
  const gpu = amdPciGpuFromLspciLine(
    '05:00.0 "VGA compatible controller" "NVIDIA Corporation" "Device 2c02" -ra1 -p00 "Micro-Star International Co., Ltd. [MSI]" "Device 5310"'
  );
  assert.equal(gpu, null);
});

test("AMD PCI fallback recognizes AMD display vendors", () => {
  const gpu = amdPciGpuFromLspciLine(
    '0b:00.0 "VGA compatible controller" "Advanced Micro Devices, Inc. [AMD/ATI]" "Navi 31 [Radeon RX 7900 XTX]" -rc8 -p00 "Sapphire Technology Limited" "Device e471"'
  );
  assert.equal(gpu.vendor, "amd");
  assert.equal(gpu.runtime, "none");
  assert.match(gpu.name, /Advanced Micro Devices/);
  assert.match(gpu.name, /Radeon RX 7900 XTX/);
});
