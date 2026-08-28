#!/usr/bin/env bash
# Copy this repository to the GPU host. Source of truth remains the local Git repo.
# Default is additive (no --delete). Secrets and virtualenvs are excluded.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -f .env.local ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env.local
  set +a
fi
: "${GPU_SSH_HOST:?GPU_SSH_HOST is required}"
: "${GPU_SSH_PORT:?GPU_SSH_PORT is required}"
: "${GPU_SSH_USER:=root}"
: "${GPU_SSH_KNOWN_HOSTS:=$ROOT/.ssh/known_hosts}"
REMOTE_DIR="${REMOTE_DIR:-/workspace/inference-platform}"
if [[ "${INFERENCE_ALLOW_REMOTE:-0}" != "1" ]]; then
  echo "Refusing to copy files while INFERENCE_ALLOW_REMOTE is not 1."
  echo "The GPU filesystem is ephemeral; wait until vLLM has finished loading."
  exit 2
fi
SSH_OPTS=(-p "$GPU_SSH_PORT" -o BatchMode=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=${GPU_SSH_KNOWN_HOSTS}")
if [[ -n "${GPU_SSH_IDENTITY_FILE:-}" ]]; then
  SSH_OPTS+=(-i "$GPU_SSH_IDENTITY_FILE" -o IdentitiesOnly=yes)
fi
rsync -az \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude '.env' \
  --exclude '.env.local' \
  --exclude '.ssh/' \
  --exclude 'artifacts/' \
  --exclude 'id_*' \
  --exclude '*.pem' \
  -e "ssh ${SSH_OPTS[*]}" \
  "$ROOT/" \
  "${GPU_SSH_USER}@${GPU_SSH_HOST}:${REMOTE_DIR}/"
echo "Copied repository to ${REMOTE_DIR} (secrets excluded)."
