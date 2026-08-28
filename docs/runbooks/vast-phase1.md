# Vast Phase 1 runbook (client path)

Use this after the remote vLLM process has **finished loading**. Do not interrupt load.

## 1. Connection

Copy `.env.example` to `.env.local` and set `GPU_SSH_HOST`, `GPU_SSH_PORT`, `GPU_SSH_USER`, `GPU_INSTANCE_ID`, and serving overrides. Do not commit that file.

The tooling never reads private-key files into Python. Use the SSH agent.

```bash
make ssh-scan-host
make tunnel
```

Default tunnel: `localhost:8000` → remote `127.0.0.1:18000`.

## 2. Authentication

- SSH tunnel to localhost: `VLLM_API_KEY` may be empty.
- Public Vast URL: `VLLM_API_KEY` is required. Never paste the value into commands that will be committed or logged.

## 3. Health

```bash
make check_vllm_health 2>/dev/null || ./scripts/check_vllm_health.sh
```

## 4. Tests (do not run while the model is loading)

```bash
export RUN_PHASE1=1
export INFERENCE_PROFILE=vast-single-gpu
make test-phase1
make benchmark-phase1 PROFILE=vast-single-gpu
```

Raw results land in gitignored `artifacts/phase1/`. Sanitize before any commit.

## 5. Remote discovery

```bash
INFERENCE_ALLOW_REMOTE=1 make preflight-remote
```

Discovery uses `nvidia-smi` and `pip show`. It does not `import torch` or `import vllm`, which can initialize CUDA.

## 6. Ephemeral disk

There is no persistent volume. The Git repository on the authoring machine is the source of truth. `make sync-remote` copies the tree without secrets and without `--delete`.
