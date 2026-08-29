# Docker notes

The repository-owned Docker path is **live-validated** for one pinned 1.5B AWQ
container on GPU 0. It passed health, model discovery, metrics, and 10/10
concurrent SSE over SSH-tunneled loopback, then shut down cleanly. See
[compose-1.5b-status.md](../docs/runbooks/compose-1.5b-status.md).

The Dockerfile is a thin wrapper around the pinned official image:

`vllm/vllm-openai:v0.27.1@sha256:c2f3b1b964e47809b722b5e75b61b1e7b39a50f70388cf2bf2418f16a9f31da2`

(linux/amd64 digest recorded 2026-08-11 from Docker Hub tag `v0.27.1`).

A future rental may advertise a different CUDA compatibility level. Validate
the pinned image against the discovered driver during remote preflight. Do not
turn one rental's CUDA value into a project-wide invariant.

`restart: "no"` is intentional so tests observe crashes instead of silent loops.
Shared memory uses `shm_size: 8gb` plus `ipc: host` as the reviewed strategy.

Compose GPU allocation requires a Linux NVIDIA container runtime. It will not
run on the macOS authoring workstation. If `gpus: all` fails with an empty
device driver, configure the toolkit for Docker (`nvidia-ctk runtime configure
--runtime=docker`) and restart Docker. Do not rewrite the k3s containerd
template.

## Environment interpolation

Docker Compose `env_file:` injects variables **into the container**. It does
**not** supply values for `${VAR}` interpolation in `compose.yaml`. Make targets
use `COMPOSE_ENV_FILE` (default `.env.local`), export a merged file under
`artifacts/compose.env`, and pass `--env-file` to Compose. `make compose-env-check`
fails if that file is missing or if the selected profile disagrees with the env
file on model, revision, tensor-parallel size, or context length.

## Network exposure

Published ports default to `127.0.0.1:${HOST_PORT}`. That is the SSH-tunneled
development bind. The process inside the container still uses `--host 0.0.0.0`
so the published port can reach it. Do not publish raw vLLM on every host
interface by default.

`VLLM_API_KEY` does not authenticate every vLLM endpoint. Health and metrics may
remain unauthenticated. External production exposure needs an authenticating
reverse proxy or firewall plus verified TLS. The completed lab had no public
external boundary; it used loopback plus SSH and the rental was destroyed.

There is no fixed `container_name`; a hard-coded name blocks Compose replica
scaling.
