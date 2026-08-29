# Vast Phase 1 runbook (client path)

> Historical/reproducibility runbook. Phase 1 passed and the rental was later
> destroyed. See [Final project status](../project-status.md) for the final
> system rather than treating this page as a request to start infrastructure.

Use this after the remote vLLM process has **finished loading**. Do not interrupt load.

## 1. Connection

Copy `.env.example` to `.env.local` and set `GPU_SSH_HOST`, `GPU_SSH_PORT`, `GPU_SSH_USER`, `GPU_INSTANCE_ID`, and serving overrides. Do not commit that file.

The tooling never reads private-key files into Python. Use the SSH agent.

Host keys go in the project file `.ssh/known_hosts` (gitignored), not `~/.ssh/known_hosts`.

```bash
# Compare the printed SHA256 fingerprint out of band, then:
EXPECTED_FINGERPRINT=SHA256:... make ssh-scan-host
# or, after you have compared it yourself:
CONFIRM=yes make ssh-scan-host
make tunnel
```

Default tunnel: `localhost:8000` → remote `127.0.0.1:18000`.

## 2. Authentication and exposure

- SSH tunnel to localhost: `VLLM_API_KEY` may be empty.
- `VLLM_API_KEY` does not protect every vLLM endpoint. Health and metrics may remain unauthenticated.
- Do not publish Compose ports on `0.0.0.0` for development. Default `HOST_BIND=127.0.0.1`.
- External production exposure requires an authenticating reverse proxy or firewall. The Vast portal authenticated reverse proxy is the current external boundary. Never paste the API key into commands that will be committed or logged.

## 3. Health

Ready means HTTP **200** only. 401, 404, 3xx, and 5xx are not ready.

```bash
make health
```

## 4. Tests (do not run while the model is loading)

```bash
export RUN_PHASE1=1
export INFERENCE_PROFILE=vast-single-gpu
make test-phase1
make benchmark-phase1
```

Acceptance concurrency comes from `phase1_acceptance_concurrency`. Streaming checks use the raw SSE transport, including `data: [DONE]`. Prompts are expanded to the configured input-token envelope; reports label estimated or measured prompt tokens instead of assuming a short sentence is 128 tokens.

Raw results land in gitignored `artifacts/phase1/`. Sanitize before any commit.

Compose Make targets require `.env.local` (`COMPOSE_ENV_FILE`) and `PROFILE=vast-single-gpu` (`PHASE1_PROFILE`). Interpolation does not use the service `env_file:` mapping.

## 5. Remote discovery

```bash
INFERENCE_ALLOW_REMOTE=1 make preflight-remote
```

Discovery uses `nvidia-smi` and `pip show`. It does not `import torch` or `import vllm`, which can initialize CUDA.

## 6. Ephemeral disk

There is no persistent volume. The Git repository on the authoring machine is the source of truth. `make sync-remote` copies the tree without secrets and without `--delete`.
