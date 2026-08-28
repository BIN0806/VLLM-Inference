#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PROFILE="${PROFILE:-authoring}"
exec uv run python -m inference_platform.preflight --profile "$PROFILE" "$@"
