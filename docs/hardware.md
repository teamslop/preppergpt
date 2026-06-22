# Hardware Guide

PrepperGPT works best on Linux with an NVIDIA GPU and enough NVMe space for
model weights.

Recommended starting points:

- Speed profile: 16 GB RAM, 8-12 GB VRAM, 40 GB free disk.
- Balanced profile: 32-64 GB RAM, 12-24 GB VRAM, 120 GB free disk.
- Intelligence profile: 96 GB RAM or more, fast NVMe, and hundreds of GB free
  for GLM 5.2 Q4 or similar large weights.

The installer reserves about 15-20% VRAM headroom when deciding whether a model
fits. If a large manual model is selected, `preppergpt doctor` explains the
endpoint or file path that must be provided.
