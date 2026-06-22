#!/usr/bin/env bash
set -euo pipefail

if ! command -v node >/dev/null 2>&1; then
  printf 'PrepperGPT requires Node.js 20 or newer.\n' >&2
  exit 1
fi

if [[ -x "$(dirname "${BASH_SOURCE[0]}")/../bin/preppergpt.js" ]]; then
  exec node "$(dirname "${BASH_SOURCE[0]}")/../bin/preppergpt.js" install "$@"
fi

if ! command -v npx >/dev/null 2>&1; then
  printf 'PrepperGPT requires npx or a cloned preppergpt checkout.\n' >&2
  exit 1
fi

exec npx preppergpt install "$@"
