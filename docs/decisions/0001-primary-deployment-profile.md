# ADR 0001: Primary deployment profile

## Status

Accepted for Phase 0.

## Decision

The first GPU validation path is **provider `vast` + compute `single-gpu`**, not `local-1gpu`.

The macOS machine is an authoring workstation only. CUDA/vLLM acceptance runs over SSH on a Linux NVIDIA rental. Future providers reuse the same compute profiles (`single-gpu`, `multi-gpu-tp`, `multi-gpu-replicas`, `ray-single-host`, `ray-multinode`, `k8s-replica`, `k8s-replica-zero`).

The first future Kubernetes production candidate remains `k8s-replica` (one complete replica per pod, minReplicas=1). It is unvalidated.

## Consequences

- Preflight distinguishes authoring from remote GPU gates.
- Hardware is discovered, never hard-coded as project-wide truth.
- A mocked GPU or Apple Metal path cannot pass NVIDIA gates.
