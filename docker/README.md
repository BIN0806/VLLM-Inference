# Docker notes

The Dockerfile is a thin wrapper around the pinned official image:

`vllm/vllm-openai:v0.27.1@sha256:c2f3b1b964e47809b722b5e75b61b1e7b39a50f70388cf2bf2418f16a9f31da2`

(linux/amd64 digest recorded 2026-08-11 from Docker Hub tag `v0.27.1`).

A Vast.ai rental may use a different CUDA 13.0 image. Set `VLLM_IMAGE` per host
and validate it during remote preflight. Do not assume every rental supports
CUDA 13.0.

`restart: "no"` is intentional so tests observe crashes instead of silent loops.
Shared memory uses `shm_size: 8gb` plus `ipc: host` as the reviewed strategy.

Compose GPU allocation requires a Linux NVIDIA container runtime. It will not
run on the macOS authoring workstation.

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
reverse proxy or firewall. The Vast portal authenticated reverse proxy is the
current external boundary.

There is no fixed `container_name`; a hard-coded name blocks Compose replica
scaling.
