# PrepperGPT

PrepperGPT packages a local-first ChatGPT-like experience for post-apocalyptic
or long-duration outage scenarios where hosted AI services are unavailable. It
uses upstream OpenWebUI for the app shell and adds a hardware detector, model
planner, Docker Compose runtime, local sidecars, and a practical PrepperGPT
field-kit theme.

PrepperGPT supports Linux first, including NVIDIA CUDA GPUs, Linux AMD ROCm
GPUs, and CPU fallback where possible. Windows users should install and run it
inside WSL2; native Windows installs are intentionally rejected until the native
runtime path is reliable. It is an online installer: model and container
downloads require a working network during setup.

PrepperGPT optimizes for survivability over cloud-like latency. On very large
local models, very low tokens/sec is acceptable because the alternative in the
target scenario is no assistant at all.

## Install

Install from npm:

```bash
npx preppergpt install --profile balanced
preppergpt start
```

Or install globally:

```bash
npm install -g preppergpt
preppergpt install --profile balanced
preppergpt start
```

GitHub source install:

```bash
git clone https://github.com/teamslop/preppergpt.git
cd preppergpt
node bin/preppergpt.js install --profile balanced
node bin/preppergpt.js start
```

Windows users should install Ubuntu in WSL2, enable Docker Desktop's WSL
integration, and run the npm or GitHub install commands inside the WSL2 shell.

Other profiles:

```bash
preppergpt install --profile intelligence
preppergpt install --profile speed
```

Open the app at:

```text
http://127.0.0.1:8080
```

Default local admin credentials are written to `~/.preppergpt/.env.preppergpt`.
Change them before exposing the machine to any network.

## Commands

```bash
preppergpt detect
preppergpt plan --profile balanced
preppergpt install --profile balanced
preppergpt start
preppergpt stop
preppergpt status
preppergpt doctor
preppergpt switch-profile --profile speed
preppergpt bundle whisper
```

## Profiles

- `intelligence`: chooses the strongest local reasoning route that fits the
  machine, preferring GLM 5.2 Q8 on enterprise hardware, then GLM 5.2 Q4, then
  long-context coding routes when available.
- `speed`: chooses smaller GPU-friendly routes and makes low-latency chat the
  default. NVIDIA hosts use CUDA container access; Linux AMD hosts use the
  Ollama ROCm image and ROCm device mounts when ROCm is detected.
- `balanced`: uses the local auto-router as the default and keeps reasoning,
  coding, research, vision, image, and STT routes additive.

The planner never removes existing OpenWebUI models. It writes additive defaults
and route ordering into the generated compose override.

## Model Assets

PrepperGPT installs a bundled local Whisper Base STT cache during
`preppergpt install`. It is stored under `~/.preppergpt/data/models/whisper/base`
by default and mounted into OpenWebUI, so speech-to-text works from local files
after setup.

Some other routes can be pulled by the runtime, while very large routes such as
GLM 5.2 Q8/Q4 and Flux weights are marked as manual or external in
`profiles/models.json`. `preppergpt doctor` reports which selected routes still
need local files or endpoints.

AMD acceleration requires a Linux ROCm host with `rocm-smi` or `rocminfo`
available. AMD cards detected without ROCm stay on CPU-compatible routes and
receive a doctor warning instead of a broken GPU configuration.

The GLM 5.2 Q8 route is intended for an enterprise/off-grid bunker-class host:
large RAM, fast NVMe, and patience for slow local generation when no hosted
service remains available.

## Publishing

The package is designed to be published as:

```bash
npm publish --access public
```

Publishing requires an authenticated npm account with permission to publish the
`preppergpt` package.

The source repository is expected at:

```text
https://github.com/teamslop/preppergpt
```
