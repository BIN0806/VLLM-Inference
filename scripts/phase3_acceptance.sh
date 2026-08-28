#!/usr/bin/env bash
# Phase 3 acceptance. Offline by default. Live GPU tests only when RUN_PHASE3=1.
# Does not install k3s, rent hardware, or kubectl apply.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "Phase 3 offline checks (no GPU, no cluster)"
uv run ruff format --check src tests scripts benchmarks
uv run ruff check src tests scripts benchmarks
uv run pytest tests/unit/test_k8s_render.py tests/unit/test_k8s_host.py \
  tests/unit/test_transport_guard.py tests/unit/test_repo_guards.py \
  tests/unit/test_topology.py tests/unit/test_config.py -m unit --tb=short

if [[ "${RUN_PHASE3:-}" == "1" ]]; then
  echo "Phase 3 live acceptance against VLLM_BASE_URL (SSH-tunneled loopback)"
  INFERENCE_PROFILE="${INFERENCE_PROFILE:-vast-k3s-replica}" \
    uv run pytest tests/integration/test_phase3.py -m gpu --tb=short
else
  echo "Skipping live GPU/SSE tests (set RUN_PHASE3=1 after the replica is Ready)."
fi
