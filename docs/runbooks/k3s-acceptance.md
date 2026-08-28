# Phase 3 acceptance (client path)

Use after a single warm vLLM replica is **Ready** behind SSH-tunneled loopback.
Do not run this while the model is loading. Do not apply manifests from here.

Profile default: `vast-k3s-replica` (pinned 1.5B AWQ). Override only with an
explicit `INFERENCE_PROFILE` (for example `vast-k3s-replica-9b` after VRAM
discovery).

## Offline (no GPU, no cluster)

```bash
./scripts/phase3_acceptance.sh
```

This runs Ruff plus unit tests for rendering, host preflight, transport
security, topology fail-closed behavior, and repo guards.

## Live (SSH tunnel)

1. On the GPU VM: `kubectl -n inference port-forward svc/vllm 8000:8000 --address 127.0.0.1`
2. On the Mac: `make tunnel` with `VLLM_REMOTE_HOST=127.0.0.1` and
   `VLLM_REMOTE_PORT=8000` (or 18000 if you forward that port instead).
3. `VLLM_BASE_URL=http://127.0.0.1:8000`

```bash
RUN_PHASE3=1 INFERENCE_PROFILE=vast-k3s-replica ./scripts/phase3_acceptance.sh
```

Checks (same contract as Phase 1):

- `GET /health` HTTP 200
- `GET /v1/models` contains the configured live id
- `GET /metrics` HTTP 200 with a non-empty body
- Concurrent SSE streams with non-empty output and `data: [DONE]`
- Base URL is loopback unless `ALLOW_INSECURE_REMOTE_HTTP` is explicitly set

GitHub Actions does **not** run the live GPU job.
