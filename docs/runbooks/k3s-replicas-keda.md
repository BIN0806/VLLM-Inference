# Phase 4B: KEDA 1→2→1 on the vLLM StatefulSet

> Historical/reproducibility procedure for Phase 4B. Phase 4C later replaced
> the live scaler for 0→1, and the VM was destroyed during final closeout.
> The STOP rules below preserve safe gate isolation. See
> [Final project status](../project-status.md).

Single-node k3s, two GPUs, one warm 1.5B AWQ replica. Prove a **manual**
second replica first, then install **KEDA 2.20.2 only** (no HTTP add-on) and
scale 1→2→1 on aggregated `vllm:num_requests_waiting`.

Access is SSH plus `kubectl port-forward` to loopback. Do not publish
NodePort or a public HTTP URL. Do not set `minReplicaCount` to 0. Do not
deploy 9B. Do not destroy the VM from this gate.

Live sanitized closeout:
[k3s-replicas-keda-status.md](k3s-replicas-keda-status.md).

## Pins

| Component | Pin | Source |
|---|---|---|
| KEDA | `2.20.2` | `configs/pins.yaml` / kedacore/charts |
| KEDA HTTP Add-on | not installed | later scale-to-zero profile |
| Prometheus | kube-prometheus-stack `88.6.0` | Phase 4A |
| ScaledObject (historical) | `infra/keda/scaledobject-vllm-prometheus.yaml` | Phase 4B; do not apply with the HTTP SO |

## Manual second replica (required before Helm)

1. Confirm StatefulSet `vllm` is **replicas=1**, `vllm-0` Ready, GPU 1 idle.
2. `kubectl -n inference scale sts/vllm --replicas=2`.
3. Record create / container start / Ready times for `vllm-1`.
4. Confirm host GPU 1 is allocated (container CUDA index may still be 0).
5. Confirm `model-cache-vllm-1` is Bound on a different volume from ordinal 0.
6. Confirm two Ready Service endpoints and two `vllm-metrics` targets **up**.
7. Prove both pods serve HTTP 200. Do not trust `kubectl port-forward` to a
   ClusterIP Service for load-balancing; use in-cluster DNS.
8. Record host RAM, disk, both GPU allocations, and per-pod cgroup RSS.
9. Scale back to 1. Confirm GPU 1 idle and `model-cache-vllm-1` retained.
10. Stop if two replicas exceed safe memory, disk, or GPU limits.

## KEDA

```bash
helm repo add kedacore https://kedacore.github.io/charts
helm upgrade --install keda kedacore/keda \
  --version 2.20.2 \
  --namespace keda \
  --create-namespace \
  --wait --timeout 10m
kubectl apply -f infra/keda/scaledobject-vllm-prometheus.yaml
```

Do **not** install `keda-add-ons-http`. Confirm the ScaledObject targets
`apiVersion: apps/v1`, `kind: StatefulSet`. The Prometheus trigger uses
`metricType: Value` and `sum(vllm:num_requests_waiting)` so the HPA sees a
single total queue-depth scalar. `AverageValue` would multiply that total by
replica count and run away to `maxReplicaCount`.

`ignoreNullValues: "false"` makes a lost Prometheus target fail visibly.
`activationThreshold` is unused while min replicas is 1. HPA scale-down
stabilization is 300 seconds.

Generate a **sustained** waiting queue (`max_num_seqs=2` saturates running
at 2; short bursts miss the 15 s scrape). Keep requests running through
scale-out. After load ends, wait the stabilization window for 2→1.

`kubectl port-forward` to the ClusterIP Service pins one endpoint. To prove
both replicas serve, use an in-cluster client against `svc/vllm` with a new
TCP connection per request (`Connection: close`). Do not treat headless DNS
or port-forward as a distribution test.

## Out of scope (STOP)

- Scale-to-zero / HTTP interceptor
- Public ports, Ingress, NodePort, LoadBalancer
- `Qwen/Qwen3.5-9B`
- Merging `phase-4`
- Destroying the VM
