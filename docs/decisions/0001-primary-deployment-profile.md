# ADR 0001: Primary deployment profile

## Status

Accepted and exercised through the completed Phase 4 lab.

## Decision

The first GPU validation path is **provider `vast` + compute `single-gpu`**, not `local-1gpu`.

The macOS machine is an authoring workstation only. CUDA/vLLM acceptance runs over SSH on a Linux NVIDIA rental. Future providers reuse the same compute profiles (`single-gpu`, `multi-gpu-tp`, `multi-gpu-replicas`, `ray-single-host`, `ray-multinode`, `k8s-replica`, `k8s-replica-zero`).

The Kubernetes lab progressed from `k8s-replica` (one warm replica) to
`k8s-replicas` (one complete replica per GPU). Phase 3 accepted the first
topology for 1.5B AWQ on single-node k3s. Phase 4 accepted Prometheus
observability, KEDA 1→2→1, and HTTP-interceptor 0→1→0 on a two-GPU
single-node k3s VM. EKS, GKE, multi-node Kubernetes, production TLS/HA, and
9B autoscaling remain unvalidated.

## Consequences

- Preflight distinguishes authoring from remote GPU gates.
- Hardware is discovered, never hard-coded as project-wide truth.
- A mocked GPU or Apple Metal path cannot pass NVIDIA gates.
