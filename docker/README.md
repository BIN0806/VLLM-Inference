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
