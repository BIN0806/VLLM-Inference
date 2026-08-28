#!/usr/bin/env bash
# Open an SSH tunnel to the remote vLLM bind address.
# Uses the SSH agent. Never prints key material. Never disables host-key checks.
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
: "${VLLM_REMOTE_HOST:=127.0.0.1}"
: "${VLLM_REMOTE_PORT:=18000}"
: "${VLLM_LOCAL_TUNNEL_PORT:=8000}"
SSH_OPTS=(
  -p "$GPU_SSH_PORT"
  -l "$GPU_SSH_USER"
  -o BatchMode=yes
  -o StrictHostKeyChecking=yes
  -o PasswordAuthentication=no
  -o KbdInteractiveAuthentication=no
  -o PreferredAuthentications=publickey
  -o "UserKnownHostsFile=${GPU_SSH_KNOWN_HOSTS}"
  -o ExitOnForwardFailure=yes
  -N
  -L "${VLLM_LOCAL_TUNNEL_PORT}:${VLLM_REMOTE_HOST}:${VLLM_REMOTE_PORT}"
)
if [[ -n "${GPU_SSH_IDENTITY_FILE:-}" ]]; then
  SSH_OPTS+=(-i "$GPU_SSH_IDENTITY_FILE" -o IdentitiesOnly=yes)
fi
echo "Tunnel localhost:${VLLM_LOCAL_TUNNEL_PORT} -> remote ${VLLM_REMOTE_HOST}:${VLLM_REMOTE_PORT} via SSH"
echo "Host key checking is enabled. Use make ssh-scan-host for first contact."
exec ssh "${SSH_OPTS[@]}" "$GPU_SSH_HOST"
