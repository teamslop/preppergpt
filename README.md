# PrepperGPT

PrepperGPT packages a local-first ChatGPT-like experience for Linux machines.
It uses upstream OpenWebUI for the app shell and adds a hardware detector,
model planner, Docker Compose runtime, local sidecars, and a practical
PrepperGPT field-kit theme.

The first release targets Linux with NVIDIA GPUs first, with CPU fallback where
possible. It is an online installer: model and container downloads require a
working network during setup.

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
```

## Profiles

- `intelligence`: chooses the strongest local reasoning route that fits the
  machine, preferring GLM 5.2 Q4 and long-context coding routes when available.
- `speed`: chooses smaller GPU-friendly routes and makes low-latency chat the
  default.
- `balanced`: uses the local auto-router as the default and keeps reasoning,
  coding, research, vision, image, and STT routes additive.

The planner never removes existing OpenWebUI models. It writes additive defaults
and route ordering into the generated compose override.

## Model Assets

Some routes can be pulled by the runtime, while very large routes such as GLM
5.2 Q4 and Flux weights are marked as manual or external in
`profiles/models.json`. `preppergpt doctor` reports which selected routes still
need local files or endpoints.

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
