#!/usr/bin/env bash
# Capture a candidate SSH host key, print its SHA256 fingerprint, and install
# it only after an expected fingerprint, a matching trusted known_hosts file,
# or explicit confirmation.
# Does not disable StrictHostKeyChecking. Default destination is the project
# .ssh/known_hosts file, not ~/.ssh/known_hosts.
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
DEST="${GPU_SSH_KNOWN_HOSTS:-$ROOT/.ssh/known_hosts}"
TRUSTED="${TRUSTED_KNOWN_HOSTS:-$HOME/.ssh/known_hosts}"
mkdir -p "$(dirname "$DEST")" "$ROOT/artifacts"
CANDIDATE="$(mktemp "$ROOT/artifacts/hostkey.candidate.XXXXXX")"
cleanup() { rm -f "$CANDIDATE"; }
trap cleanup EXIT
echo "Fetching candidate host key (address omitted). Not trusted yet."
ssh-keyscan -p "$GPU_SSH_PORT" -T 10 "$GPU_SSH_HOST" > "$CANDIDATE"
if [[ ! -s "$CANDIDATE" ]]; then
  echo "error: ssh-keyscan returned no keys" >&2
  exit 1
fi
echo "Candidate SHA256 fingerprint(s):"
uv run python -m inference_platform.ssh_trust show --candidate "$CANDIDATE"
if [[ -n "${EXPECTED_FINGERPRINT:-}" ]]; then
  uv run python -m inference_platform.ssh_trust install \
    --candidate "$CANDIDATE" \
    --known-hosts "$DEST" \
    --expected-fingerprint "$EXPECTED_FINGERPRINT"
elif [[ "${CONFIRM:-}" == "yes" ]]; then
  uv run python -m inference_platform.ssh_trust install \
    --candidate "$CANDIDATE" \
    --known-hosts "$DEST" \
    --confirm
elif [[ -f "$TRUSTED" ]]; then
  echo "Comparing candidate to trusted known_hosts (not appending scan output blindly)."
  uv run python -m inference_platform.ssh_trust install \
    --candidate "$CANDIDATE" \
    --known-hosts "$DEST" \
    --trusted-known-hosts "$TRUSTED"
else
  echo "Refusing to install. Compare the fingerprint out of band, then rerun:" >&2
  echo "  EXPECTED_FINGERPRINT=SHA256:... make ssh-scan-host" >&2
  echo "  or CONFIRM=yes make ssh-scan-host" >&2
  exit 1
fi
echo "Installed into project known_hosts. Host-key checking remains enabled."
