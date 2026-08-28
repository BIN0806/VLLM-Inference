#!/usr/bin/env bash
# Fetch the remote SSH host key into a local known_hosts file.
# This does not disable verification; it records the key for later StrictHostKeyChecking=yes.
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
DEST="${GPU_SSH_KNOWN_HOSTS:-$HOME/.ssh/known_hosts}"
mkdir -p "$(dirname "$DEST")"
echo "Recording host key for ${GPU_SSH_HOST}:${GPU_SSH_PORT} into ${DEST}"
ssh-keyscan -p "$GPU_SSH_PORT" -T 10 "$GPU_SSH_HOST" >> "$DEST"
echo "Done. Host-key checking remains enabled."
