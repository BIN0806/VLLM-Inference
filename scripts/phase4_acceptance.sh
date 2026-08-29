#!/usr/bin/env bash
# Phase 4A acceptance. Offline by default. Live GPU/PromQL tests when RUN_PHASE4=1.
# Does not install k3s, Helm, Prometheus, or KEDA. Does not scale to two replicas.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "Phase 4A offline checks (no GPU, no cluster)"
uv run ruff format --check src tests scripts benchmarks
uv run ruff check src tests scripts benchmarks
uv run pytest tests/unit/test_k8s_render.py tests/unit/test_k8s_host.py \
  tests/unit/test_observability.py tests/unit/test_transport_guard.py \
  tests/unit/test_repo_guards.py tests/unit/test_topology.py \
  tests/unit/test_config.py -m unit --tb=short

if [[ "${RUN_PHASE4:-}" == "1" ]]; then
  echo "Phase 4A live acceptance against VLLM_BASE_URL and PROMETHEUS_BASE_URL"
  INFERENCE_PROFILE="${INFERENCE_PROFILE:-vast-k3s-replicas}" \
    PROMETHEUS_BASE_URL="${PROMETHEUS_BASE_URL:-http://127.0.0.1:9090}" \
    uv run pytest tests/integration/test_phase4.py -m gpu --tb=short
else
  echo "Skipping live GPU/SSE/PromQL tests (set RUN_PHASE4=1 after the replica is Ready)."
fi
