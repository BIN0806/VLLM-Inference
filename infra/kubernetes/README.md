# Kubernetes (unvalidated)

Phase 3+. Do not apply these manifests yet. No cluster is part of Phase 0 or Phase 1.

Target later: provider-neutral `k8s-replica` with one GPU per complete vLLM replica, `minReplicas: 1`. Overlays:

- `overlays/local` — constrained GPUs, Recreate, local storage
- `overlays/eks` — placeholders only until tested on EKS
- `overlays/gke` — placeholders only until tested on GKE

A future Vast VM running k3s may demonstrate the same portable base. Do not claim EKS, GKE, minikube, or k3s validation until those runs happen.

GPUs per pod = tensor_parallel_size × pipeline_parallel_size for a self-contained single-pod replica.

NVIDIA Device Plugin is cluster infrastructure (pinned 0.20.0 in `configs/pins.yaml`), not an application install hidden inside an app deploy command.
