# ADR 0003: Dependency version policy

## Status

Accepted for Phase 0.

## Decision

Pin exact versions or immutable digests. Never commit `latest`. Record the official source and the compatibility reason in `configs/pins.yaml`.

| Component | Pin | Source | Reason |
|---|---|---|---|
| Authoring Python | 3.12.x (`requires-python >=3.11,<3.13`) | Project policy | User-required tooling range |
| vLLM | 0.27.1 | GitHub release 2026-08-11 | Matches current rental |
| Official image linux/amd64 | sha256:c2f3b1b964e47809b722b5e75b61b1e7b39a50f70388cf2bf2418f16a9f31da2 | Docker Hub tag v0.27.1 | Reproducible wrapper image |
| openai | 3.5.0 | PyPI | Client for OpenAI-compatible API |
| httpx | 0.28.1 | PyPI | HTTP client |
| pydantic / settings | 2.13.4 / 2.15.0 | PyPI | Config |
| pytest / ruff / psutil | 9.1.1 / 0.16.5 / 7.2.2 | PyPI | Authoring tests |
| Ray (optional extra) | 2.58.0 | PyPI | Pin for later; image-bundled Ray may differ and must be discovered |
| kubernetes (optional extra) | 36.0.3 | PyPI | Pin for later |
| KubeRay | 1.7.0 | GitHub | Later |
| kube-prometheus-stack | chart 88.6.0 | prometheus-community | Phase 4A scrape (Grafana/Alertmanager off) |
| KEDA | 2.20.2 | kedacore/charts | Later |
| KEDA HTTP Add-on | 0.15.0 | kedacore/http-add-on | Later |
| NVIDIA device plugin | 0.20.0 | NVIDIA/k8s-device-plugin | Phase 3/4 cluster GPU advertise |
| NVIDIA Container Toolkit | 1.18.0-1 | NVIDIA libnvidia-container apt | Phase 4A k3s NVIDIA runtime |
| Helm | v3.16.4 | get-helm-3 | Phase 4A chart install |
| k3s | v1.34.10+k3s1 (Kubernetes v1.34.10, linux/amd64 sha256 e63a3511b2603fd1436a1ea8d228348a3b47334b45024801d41a8c0e2d22e8c4) | https://get.k3s.io / GitHub release | Phase 3/4 single-node; 1.33–1.35 window |

The Vast rental image is **not** assumed to be the official digest. Set `VLLM_IMAGE` per host. CUDA 13.0 is a property of the current rental’s driver (580.159.03), not a global invariant.

Changing a pin requires updating `configs/pins.yaml` and this ADR.

## Consequences

Authoring installs only client/test dependencies. vLLM/CUDA are not installed on macOS. Chart pins are documentation until those phases run.
