# Hardware Guide

PrepperGPT works best on Linux with an NVIDIA GPU and enough NVMe space for
model weights. It is designed for post-apocalyptic or long-duration outage
scenarios, so the high-end GLM tiers deliberately favor local availability and
answer quality over hosted-service latency.

Recommended starting points:

- Speed profile: 16 GB RAM, 8-12 GB VRAM, 40 GB free disk.
- Balanced profile: 32-64 GB RAM, 12-24 GB VRAM, 120 GB free disk.
- Intelligence profile: 96 GB RAM or more, fast NVMe, and hundreds of GB free
  for GLM 5.2 Q4 or similar large weights.
- Enterprise 8-bit GLM tier: 256 GB RAM or more, 48-80 GB VRAM preferred,
  and 1.5-2 TB of fast NVMe for GLM 5.2 Q8 plus working/cache room.

The installer reserves about 15-20% VRAM headroom when deciding whether a model
fits. If a large manual model is selected, `preppergpt doctor` explains the
endpoint or file path that must be provided.

Very low tokens/sec is acceptable for the GLM 5.2 Q8 tier because that tier is
for situations where there is no cloud model to fall back to.

## Hardware Matrix

| Tier | Typical specs | PrepperGPT routes |
| --- | --- | --- |
| Basic CPU laptop | 16 GB RAM, no GPU, 80 GB disk | `local-chatgpt-auto`, `llama3.1:8b`, `local-vision-moondream2`, bundled Whisper |
| Mid NVIDIA | 64 GB RAM, 12 GB usable VRAM, 250 GB disk | Gemma fast lane, Qwen coder fallback, local vision, bundled Whisper |
| High NVIDIA | 128 GB RAM, 24 GB VRAM, 750 GB NVMe | GLM 5.2 Q4 configured, Slopcode/Qwen configured, Gemma fast lane, Flux configured |
| Full PrepperGPT rig | 128+ GB RAM, 24+ GB VRAM, 1 TB NVMe, GLM/Slopcode/Flux files present | GLM 5.2 Q4 primary, Slopcode coding, Gemma fast lane, Deep Research, Agent, Vision, Flux, Whisper |
| Enterprise 8-bit GLM rig | 256+ GB RAM, 48-80+ GB VRAM preferred, 1.5-2 TB fast NVMe | `glm52-q8-local` primary for Max Intelligence, `glm52-q4-local` fallback, Slopcode/Qwen coding, Gemma fast lane, full sidecar stack |
