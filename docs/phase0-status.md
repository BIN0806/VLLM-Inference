# Phase 0 gate status

Recorded on the macOS authoring workstation. CUDA/vLLM GPU acceptance is **not** claimed.

This file is the Phase 0 hardening snapshot (Compose interpolation, strict readiness, raw SSE `[DONE]` validation, SSH first-contact trust, localhost bind, configuration-driven workload). Live Phase 1 was not started.

## Commands and exit status

| Command | Exit status | Notes |
|---|---|---|
| `uv run ruff format --check src tests scripts benchmarks` | 0 | After `ruff format` |
| `uv run ruff check src tests scripts benchmarks` | 0 | |
| `uv run pytest tests/unit -m unit -v` | 0 | 61 passed |
| `uv run python -m inference_platform.preflight --profile authoring` | 0 | overall `WARN` (Docker daemon down, disk headroom, undiscovered remote GPUs) |
| Remote SSH / `INFERENCE_ALLOW_REMOTE=1` | not run | Local hardening only; Vast host was not contacted |
| GPU/Ray/Kubernetes/KEDA/Prometheus gates | not run | Unclaimed |

A `WARN` overall is not a `FAIL`. Mandatory authoring checks passed. NVIDIA, Ray, and Kubernetes were `SKIP` as required for this host.

Machine-readable report: gitignored `artifacts/phase0/preflight.json` (redacted, `gpu_gate_claimed: false`).

Foundation commit: `109b86e`. Hardening commit: `c2a844951bb65c5c6169df5d1e786065b39107fe` (branch `phase-0`).

## Frozen pins (see `configs/pins.yaml`)

- Python authoring: 3.12.12 (`requires-python >=3.11,<3.13`)
- vLLM: 0.27.1
- Official image linux/amd64: `vllm/vllm-openai:v0.27.1@sha256:c2f3b1b964e47809b722b5e75b61b1e7b39a50f70388cf2bf2418f16a9f31da2`
- Baseline model: `Qwen/Qwen2.5-1.5B-Instruct-AWQ` @ `3ecffa0ceb27851800f45519bab9c457a04405e1` (Apache-2.0)
- Validation override: `Qwen/Qwen3.5-9B` @ `c202236235762e1c871ad0ccb60c8ee5ba337b9a` (Apache-2.0)
- KEDA 2.20.2, HTTP add-on 0.15.0, KubeRay 1.7.0, kube-prometheus-stack 88.6.0, NVIDIA device plugin 0.20.0 (documented, not installed)

## Assumptions that affect later gates

- Provider `vast` + compute `single-gpu` is the GPU validation target. This Mac is authoring-only.
- 5,000 output tokens/sec is aspirational, not a Phase 1 fail condition.
- Multi-node Ray: `NOT RUN — HARDWARE UNAVAILABLE`.
- Kubernetes overlays are unvalidated examples.
- Remote mutations were not executed. Do not interrupt a loading vLLM process.
- Compose interpolation requires `COMPOSE_ENV_FILE` (default `.env.local`); service `env_file:` is not a substitute.
- Health ready means HTTP 200 only. Phase 1 streaming acceptance uses the raw SSE parser, including `data: [DONE]`.

Phase 0 local gate remains complete after this hardening. Phase 1 live tests wait for explicit approval after vLLM startup is confirmed finished.
