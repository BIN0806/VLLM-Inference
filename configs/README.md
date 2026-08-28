# Independent configuration layers
#
# 1. Provider / connection  (.env.local + configs/providers/*.example)
# 2. Hardware topology      (discovered JSON + configs/compute/*)
# 3. Model                  (configs/models/*)
# 4. Serving                (configs/serving/* + VLLM_* env)
# 5. Workload / benchmark   (configs/workloads/*)
# 6. Deployment environment (authoring Mac vs GPU host vs future Kubernetes)
#
# A composed profile under configs/profiles/ names those layers.
# Changing a Vast rental should normally require only provider/connection
# and hardware values, not a rewrite of model or workload files.

layers:
  - provider
  - compute
  - model
  - serving
  - workload
  - environment

compute_profiles:
  - single-gpu
  - multi-gpu-tp
  - multi-gpu-replicas
  - ray-single-host
  - ray-multinode
  - k8s-replica
  - k8s-replica-zero

# Composed Phase 3 candidates (unvalidated; do not provision from this repo):
#   vast-k3s-replica      — 1.5B AWQ, one GPU, k3s
#   vast-k3s-replica-9b   — 9B opt-in after VRAM discovery

