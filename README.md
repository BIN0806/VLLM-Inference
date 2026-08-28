# Distributed vLLM inference platform

Inference serving only. This repository does not contain training, fine-tuning,
dataset, gradient, optimizer, or checkpoint-training code.

Secrets, live SSH hosts, API keys, private keys, and `.env.local` are never
committed. Copy `.env.example` to gitignored `.env.local` on the authoring
machine.

## Roles

| Role | What it is | What it is not |
|---|---|---|
| Authoring workstation | Docs, lint, unit tests, API client | CUDA / vLLM GPU execution |
| Compute `single-gpu` | One complete replica on one GPU | A provider name |
| Provider `vast` | Connection overlay for a rental | Hard-coded IPs or GPU SKUs |
| Tensor parallelism | One replica sharded across GPUs | Horizontal request scaling |
| Independent replicas | One replica per GPU for throughput | The same thing as TP |
| Kubernetes `k8s-replica` | One complete pod per replica, min=1 | Phase 3 1.5B AWQ on k3s accepted; KEDA not installed |
| Scale-to-zero | Later profile behind a durable HTTP interceptor | Something vLLM metrics can do alone |

Tensor parallelism and pipeline parallelism build **one complete model replica**.
KEDA (later) adds or removes **whole replicas**. Scaling a single TP rank or Ray
worker would break the replica.

vLLM Prometheus metrics disappear when no replica exists. Scale-to-zero therefore
needs a durable front door such as the KEDA HTTP Add-on interceptor.

## Phase 0 status

Phase 0 freezes versions, configuration layers, preflight, and the benchmark
contract.

Current portable baseline (temporary rental, not a project-wide default):

- Provider: `vast`
- Compute profile: `single-gpu` for Phase 1/2; `k8s-replica` on k3s for Phase 3
- Portable baseline model: `Qwen/Qwen2.5-1.5B-Instruct-AWQ` @ `3ecffa0ceb27851800f45519bab9c457a04405e1`
- Phase 2 override: `Qwen/Qwen3.5-9B` @ `c202236235762e1c871ad0ccb60c8ee5ba337b9a` (not used in Phase 3)
- vLLM: `0.27.1` with official image digest recorded in `configs/pins.yaml`

Phase 3 accepted one warm 1.5B AWQ replica on single-node k3s. 9B, Ray,
Prometheus, KEDA, and scale-to-zero are **not claimed**.

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
skip that proxy and may omit the key. The client refuses to send
`VLLM_API_KEY` or `OPEN_BUTTON_TOKEN` to a non-loopback `http://` URL unless
`ALLOW_INSECURE_REMOTE_HTTP=true` (lab-only, default false). Never put the key
in YAML, Git, or reports. Phase 2 should use an SSH tunnel unless HTTPS is
configured.

## Configuration layers

See `configs/README.md`. Changing a Vast rental should normally require only
provider/connection and hardware values in `.env.local`.

## Later phases (not in this snapshot)

Ray, KEDA, and observability READMEs stay local until those phases are
implemented. They are gitignored so GitHub only has placeholders under
`infra/`. Phase 3 accepted one warm 1.5B AWQ replica on single-node k3s
([status](docs/runbooks/k3s-replica-1.5b-status.md)). 9B, Ray, Prometheus,
KEDA, and scale-to-zero were not tested. Do not rent or install a later gate
from this repository until that gate is approved.

## Commands

Run `make help`. Teardown and sync targets use explicit compose project names
and rsync excludes. They do not delete unrelated user resources. Remote sync
and remote preflight refuse to run until `INFERENCE_ALLOW_REMOTE=1`.
