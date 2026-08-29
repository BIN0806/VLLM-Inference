# Distributed vLLM inference platform

Inference serving only. This repository does not contain training, fine-tuning,
dataset, gradient, optimizer, or checkpoint-training code.

Secrets, live SSH hosts, API keys, private keys, and `.env.local` are never
committed. Copy `.env.example` to gitignored `.env.local` on the authoring
machine.

## Documentation map

- [Architecture](docs/architecture.md) — topology and scaling boundaries.
- [Architecture decisions](docs/decisions/README.md) — decisions, alternatives,
  evidence, and consequences.
- [Benchmark contract](docs/benchmark-contract.md) — workload and measurement
  rules.
- [Operations](docs/operations.md) — approved runbooks and current gates.
- [Security](docs/security.md) — credential, transport, and ephemeral-host
  boundaries.

## Roles

| Role | What it is | What it is not |
|---|---|---|
| Authoring workstation | Docs, lint, unit tests, API client | CUDA / vLLM GPU execution |
| Compute `single-gpu` | One complete replica on one GPU | A provider name |
| Provider `vast` | Connection overlay for a rental | Hard-coded IPs or GPU SKUs |
| Tensor parallelism | One replica sharded across GPUs | Horizontal request scaling |
| Independent replicas | One replica per GPU for throughput | The same thing as TP |
| Kubernetes `k8s-replica` | One complete pod per replica, min=1 | Phase 3 1.5B AWQ on k3s accepted |
| Kubernetes `k8s-replicas` | StatefulSet, one GPU per pod, max=2 | Phase 4C HTTP interceptor lab; Phase 4B 1→2→1 historical |
| Scale-to-zero | Lab path behind KEDA HTTP Add-on 0.15.0 | Something vLLM metrics can do alone; not HTTP 0→2 or production serverless |

Tensor parallelism and pipeline parallelism build **one complete model replica**.
KEDA adds or removes **whole replicas**. Scaling a single TP rank or Ray
worker would break the replica.

vLLM Prometheus metrics disappear when no replica exists. Scale-to-zero therefore
needs a durable front door such as the KEDA HTTP Add-on interceptor.

## Phase 0 status

Phase 0 freezes versions, configuration layers, preflight, and the benchmark
contract.

Current portable baseline (temporary rental, not a project-wide default):

- Provider: `vast`
- Compute profile: `single-gpu` for Phase 1/2; `k8s-replica` on k3s for Phase 3; `k8s-replicas` for Phase 4A
- Portable baseline model: `Qwen/Qwen2.5-1.5B-Instruct-AWQ` @ `3ecffa0ceb27851800f45519bab9c457a04405e1`
- Phase 2 override: `Qwen/Qwen3.5-9B` @ `c202236235762e1c871ad0ccb60c8ee5ba337b9a` (not used in Phase 3)
- vLLM: `0.27.1` with official image digest recorded in `configs/pins.yaml`

Phase 3 accepted one warm 1.5B AWQ replica on single-node k3s. Phase 4A
accepted Prometheus scrape of one StatefulSet replica. Phase 4B accepted
Prometheus-driven KEDA **1→2→1**. Phase 4C accepted interceptor-driven lab
**0→1** (one non-retried held request, 150 s Ready, HTTP 200 SSE) and a
normal second **1→0** (~327 s). HTTP **0→2**, 9B autoscaling, Ray,
production TLS/HA, and managed Kubernetes are **not claimed**. Repository
Docker Compose served one 1.5B AWQ container on GPU 0 over SSH-tunneled
loopback after k3s stopped; see
[compose-1.5b-status.md](docs/runbooks/compose-1.5b-status.md).

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

## Later phases (not claimed)

Tracked Phase 3–4C runbooks live under `docs/runbooks/`. Infra operator
READMEs stay gitignored placeholders. Do not claim multi-node Ray, managed
Kubernetes, production TLS/HA, HTTP 0→2, 9B autoscaling, or 5,000 output
tokens/s. Do not rent or install a later gate from this repository until
that gate is approved.

## Commands

Run `make help`. Teardown and sync targets use explicit compose project names
and rsync excludes. They do not delete unrelated user resources. Remote sync
and remote preflight refuse to run until `INFERENCE_ALLOW_REMOTE=1`.
