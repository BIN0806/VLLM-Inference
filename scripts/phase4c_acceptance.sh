#!/usr/bin/env bash
# Phase 4C offline checks. Does not install charts or mutate a cluster.
# Live GPU/interceptor tests stay on the rental via the HTTP runbook.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "Phase 4C offline checks (no GPU, no cluster mutation)"
uv run ruff format --check src tests scripts benchmarks
uv run ruff check src tests scripts benchmarks
uv run pytest tests/unit -m unit --tb=short

if command -v helm >/dev/null 2>&1; then
  echo "Rendering kedacore/keda-add-ons-http 0.15.0"
  ./scripts/keda_http_render.sh
else
  echo "Skipping helm template (helm not on PATH). CI installs Helm 3.16.4."
fi
