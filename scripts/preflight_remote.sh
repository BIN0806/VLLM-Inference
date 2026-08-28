#!/usr/bin/env bash
# Read-only remote preflight. Refuses to run unless INFERENCE_ALLOW_REMOTE=1.
# Never stops, restarts, or kills vLLM.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ "${INFERENCE_ALLOW_REMOTE:-0}" != "1" ]]; then
  echo "Remote preflight is disabled."
  echo "Set INFERENCE_ALLOW_REMOTE=1 only after vLLM startup is reported complete."
  echo "This script is read-only and will not mutate the GPU host."
  exit 2
fi
PROFILE="${PROFILE:-vast-single-gpu}"
exec uv run python -m inference_platform.hardware --remote
