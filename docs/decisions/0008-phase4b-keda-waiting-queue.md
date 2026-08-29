# ADR 0008: KEDA scales the StatefulSet on total waiting queue depth

## Status

Accepted for Phase 4B. Live 1→2→1 evidence is in
[k3s-replicas-keda-status.md](../runbooks/k3s-replicas-keda-status.md).

## Context

Phase 4A proved Prometheus scrape of `vllm:num_requests_waiting` per replica.
Phase 4B needs KEDA to add a second complete TP=1 replica when one warm
replica is saturated, then remove it after demand falls, without scale-to-zero
and without the HTTP add-on.

`max_num_seqs=2` caps `vllm:num_requests_running`, so running count is a poor
1→2 signal. Waiting is the overflow. The query must be one scalar. HPA
`AverageValue` treats a metric as a per-replica average and multiplies by
current replicas; a cluster-wide **total** then grows with replica count and
runs to max.

## Decision

- Install pinned KEDA **2.20.2** only. Do not install the HTTP add-on.
- Target `apiVersion: apps/v1`, `kind: StatefulSet`, `name: vllm` explicitly.
- `minReplicaCount: 1`, `maxReplicaCount: 2`.
- Trigger query `sum(vllm:num_requests_waiting)` with `metricType: Value` and
  threshold `"1"`.
- Set `ignoreNullValues: "false"` so a missing Prometheus result errors.
- Do not set `activationThreshold`; it only matters for 0→1.
- Configure HPA `scaleDown.stabilizationWindowSeconds: 300` to prevent rapid
  2→1 oscillation.

## Alternatives considered

- **`AverageValue` on the same sum.** Rejected: desired replicas would be
  `currentReplicas * totalWaiting / threshold` and stick at 2 once waiting is
  non-zero.
- **Scale on `num_requests_running`.** Rejected: it saturates at
  `max_num_seqs` and does not show overflow.
- **Per-pod queries.** Rejected: KEDA requires one scalar; two series fail.
- **`or vector(0)` in the query.** Rejected with `ignoreNullValues: "false"`:
  a lost scrape must be visible, not silently treated as idle.
- **KEDA HTTP add-on.** Required later for scale-to-zero; out of this gate.

## Evidence

- Manual 1→2: `vllm-1` received host GPU 1 and PVC `model-cache-vllm-1`.
  Cold container start → Ready 172 s. Scale-in left the PVC Bound and GPU 1
  idle.
- KEDA 2.20.2 Helm release; no HTTP add-on CRDs. HPA `keda-hpa-vllm` reported
  idle **0/1**, then **6/1** under sustained load (waiting=6).
- Automatic 1→2: detection **11 s**, warm Ready **141 s** after container
  start vs **172 s** cold. Marker `phase4b-ordinal1-cache` survived.
- Client traffic through scale-out: 193/193 HTTP 200, 0 timeouts. Automatic
  2→1 at **01:52:39** UTC, ~287 s after the metric returned to 0.

## Consequences

- 1→N capacity scaling is proven for this 1.5B AWQ StatefulSet on two GPUs.
- Scale-to-zero still needs a durable front door; vLLM series vanish at zero
  replicas.
- `kubectl port-forward` to a Service does not load-balance. Use in-cluster
  DNS when proving both replicas serve.
- Ordinal PVCs remain after scale-in on this VM and die with the VM.
