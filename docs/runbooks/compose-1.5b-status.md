# Compose validation: one 1.5B AWQ container on GPU 0

> Final accepted Compose evidence. The container was brought down and the
> rental was destroyed after this gate. See
> [Final project status](../project-status.md).

Sanitized closeout for the repository Docker Compose path. No IP addresses,
SSH ports, host keys, tokens, credentials, instance IDs, kubeconfigs, or raw
container dumps are recorded here.

**Gate decision: GO for pinned Compose 1.5B AWQ on one GPU (loopback + SSH).**
**This does not weaken the already-accepted Phase 4A, 4B, or 4C gates.**

Access was an SSH local-forward to remote `127.0.0.1:8000` only. The published
host bind stayed `127.0.0.1:8000`. No public inference listener was opened.
k3s had already been stopped with `systemctl stop k3s` (no SIGKILL) before
this gate.

HTTP **0→2 was not tested**. Phase 4B remains the Prometheus-driven **1→2**
proof. Phase 4C remains the interceptor-driven **0→1** proof. This gate is
Compose serving only.

## Hardware and software (same VM as Phase 4C)

| Item | Recorded value |
|---|---|
| Host class | Vast Ubuntu KVM VM, 10 vCPUs, 24.51 GiB RAM |
| GPU | 2× NVIDIA RTX A4000, 16376 MiB, driver 580.95.05 |
| Docker | 28.1.1 |
| Compose | v2.35.1 |
| NVIDIA Container Toolkit | `1.18.0-1` (`nvidia-ctk` 1.18.0) |
| Image | thin wrapper `inference-platform/vllm:0.27.1` from `docker/Dockerfile` |
| Upstream pin | `vllm/vllm-openai:v0.27.1@sha256:c2f3b1b964e47809b722b5e75b61b1e7b39a50f70388cf2bf2418f16a9f31da2` |
| Compose file | `docker/compose.yaml` |
| Profile | `vast-k3s-replica` (1.5B AWQ). **Not** `vast-single-gpu` (9B) |
| Model | `Qwen/Qwen2.5-1.5B-Instruct-AWQ` @ `3ecffa0ceb27851800f45519bab9c457a04405e1` |
| Served name | `qwen2.5-1.5b-instruct-awq` |
| Topology | TP=1, one container, `CUDA_VISIBLE_DEVICES=0` |
| Serving | `gpu_memory_utilization=0.9`, `max_model_len=8192`, `max_num_seqs=8` |

Weights were copied from a stopped k3s `local-path` PVC into the host
`HF_HOME` bind mount. Compose did **not** write into the live k3s volume.

## What failed first, and the safe fix

The first `docker compose up` failed with:

`could not select device driver "" with capabilities: [[gpu]]`

The NVIDIA runtime was already listed in Docker's daemon JSON, but Compose
`gpus: all` had no working GPU device driver. The operator ran
`nvidia-ctk runtime configure --runtime=docker`, generated a CDI spec, enabled
Docker `features.cdi`, and restarted Docker with systemd. That command was
**not** pointed at the k3s containerd template. k3s stayed inactive.

A `docker run --gpus all` smoke check then listed both GPUs. Compose `up`
started exactly one container.

`docker/compose.yaml` uses `gpus: all`. A remote-only override set
`CUDA_VISIBLE_DEVICES=0` and `NVIDIA_VISIBLE_DEVICES=0` so vLLM used GPU 0.
Host `nvidia-smi` showed GPU 1 at **0 MiB** while the server was Ready.

## Acceptance

| Check | Result |
|---|---|
| Compose build/pull of the pinned Dockerfile | succeeded |
| Exactly one vLLM container | `inference-platform-vllm-1` |
| Published bind | `127.0.0.1:8000->8000/tcp` only |
| Public `:8000` listener | **none** |
| GPU passthrough | GPU 0 **14150 MiB**; GPU 1 **0 MiB** |
| `/health` | HTTP **200** (~90 s from container start, cache reuse) |
| `/v1/models` | `qwen2.5-1.5b-instruct-awq` |
| `/metrics` | `vllm:*` series present (`num_requests_running=0` when idle) |
| Container memory | Docker stats **4.606 GiB** / 24.51 GiB; 115 PIDs |
| GPU worker | one `VLLM::Worker` on GPU 0, **14142 MiB** |
| 10/10 concurrent SSE | all **ok**, non-empty output, terminal, `[DONE]` |
| SSE e2e | about **404–622 ms** (1.5B AWQ, not a 9B or Phase 1 3090 comparison) |
| Client path | authoring Mac `RUN_PHASE1=1` / `INFERENCE_PROFILE=vast-k3s-replica` through `make tunnel` |

The integration artifact records `compose_used: false` because the tests
targeted an already-ready URL. The process under that URL was this Compose
container.

## Graceful shutdown

`docker compose -f docker/compose.yaml … down` stopped and removed the
container and the project network. No SIGKILL.

After down:

| Check | Result |
|---|---|
| Compose containers | none |
| `:8000` listener | gone |
| GPU compute apps | none |
| GPU 0 / GPU 1 | **0 MiB**, 0% |

## Boundaries (do not claim)

- Single-node lab; one container; one GPU.
- Not 9B, not tensor-parallel Compose, not a public bind.
- Not production TLS/HA, not a Compose replica scaler.
- HTTP **0→2**, interceptor HA, multi-node Ray, managed Kubernetes, and
  5,000 output tokens/s remain untested.
- Phase 4A/4B/4C evidence is unchanged by this report.
