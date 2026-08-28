# Distributed vLLM inference platform

Inference serving only. This repository does not contain training, fine-tuning,
dataset, gradient, optimizer, or checkpoint-training code.

## Roles

| Role | What it is | What it is not |
|---|---|---|
| Authoring workstation (this Mac) | Docs, lint, unit tests, API client | CUDA / vLLM GPU execution |
| Compute `single-gpu` | One complete replica on one GPU | A provider name |
| Provider `vast` | Connection overlay for a rental | Hard-coded IPs or GPU SKUs |
| Tensor parallelism | One replica sharded across GPUs | Horizontal request scaling |
| Independent replicas | One replica per GPU for throughput | The same thing as TP |
| Kubernetes `k8s-replica` | Complete pods scaled by KEDA, min=1 | Validated in Phase 0 |
| Scale-to-zero | Later profile behind a durable HTTP interceptor | Something vLLM metrics can do alone |

Tensor parallelism and pipeline parallelism build **one complete model replica**.
KEDA (later) adds or removes **whole replicas**. Scaling a single TP rank or Ray
worker would break the replica.

vLLM Prometheus metrics disappear when no replica exists. Scale-to-zero therefore
needs a durable front door such as the KEDA HTTP Add-on interceptor.

## Phase 0 status

Phase 0 freezes versions, configuration layers, preflight, and the benchmark
contract. GPU, Ray, Kubernetes, Prometheus, and KEDA gates are **not claimed**.

Current validation target (temporary rental, not a project-wide default):

- Provider: `vast`
- Compute profile: `single-gpu`
- Portable baseline model: `Qwen/Qwen2.5-1.5B-Instruct-AWQ` @ `3ecffa0ceb27851800f45519bab9c457a04405e1`
- Current override: `Qwen/Qwen3.5-9B` @ `c202236235762e1c871ad0ccb60c8ee5ba337b9a`
- vLLM: `0.27.1` with official image digest recorded in `configs/pins.yaml`

## Setup (authoring)

```bash
cp .env.example .env.local   # then fill GPU_SSH_* and VLLM_* (never commit)
uv sync --python 3.12 --extra dev
make lint
make test-unit
make preflight PROFILE=authoring
```

Python 3.12 is required for tooling. Python 3.14 on the Mac is not used.

## Phase 1 (after vLLM is ready)

Do not interrupt a loading vLLM process. When the user reports that startup
finished:

1. `EXPECTED_FINGERPRINT=SHA256:... make ssh-scan-host` (or `CONFIRM=yes` after
   comparing the printed fingerprint out of band). This writes
   `.ssh/known_hosts` in the repo, not `~/.ssh/known_hosts`.
2. `make tunnel` (localhost:8000 → remote 127.0.0.1:18000)
3. `RUN_PHASE1=1 make test-phase1`
4. `make benchmark-phase1`

Compose interpolation requires `COMPOSE_ENV_FILE` (default `.env.local`). Service
`env_file:` does not supply `${VAR}` values. Published ports bind to `127.0.0.1`
by default. `VLLM_API_KEY` does not protect every vLLM endpoint; the Vast portal
authenticated reverse proxy is the current external boundary. SSH-tunneled tests
may omit the key. Never put the key in YAML, Git, or reports.

## Configuration layers

See `configs/README.md`. Changing a Vast rental should normally require only
provider/connection and hardware values in `.env.local`.

## Commands

Run `make help`. Teardown and sync targets use explicit compose project names
and rsync excludes. They do not delete unrelated user resources. Remote sync
and remote preflight refuse to run until `INFERENCE_ALLOW_REMOTE=1`.
