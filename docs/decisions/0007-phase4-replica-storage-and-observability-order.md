# ADR 0007: Phase 4 replica storage and observability order

## Status

Accepted for the Phase 4 design. Phase 4A Prometheus scrape and Phase 4B
KEDA 1→2→1 are recorded in
[k3s-replicas-prometheus-status.md](../runbooks/k3s-replicas-prometheus-status.md)
and [k3s-replicas-keda-status.md](../runbooks/k3s-replicas-keda-status.md).
Phase 4C later validated HTTP-interceptor 0→1→0; HTTP 0→2 and production
TLS/HA remain unvalidated.

## Context

Phase 4 needs to demonstrate horizontal scaling from one complete vLLM replica
to two on a single k3s node with two GPUs. Each pod needs a writable Hugging Face
cache. The Phase 3 Deployment used one `local-path` ReadWriteOnce PVC, while the
Phase 4 host has enough disk but only about 24.5 GiB of guest RAM.

KEDA will eventually consume a Prometheus query. Installing a scaler before
proving the exact vLLM 0.27.1 series, scrape labels, and query cardinality would
make the scaling contract depend on assumptions.

## Decision

- Use a StatefulSet with one complete TP=1 replica and one GPU per pod.
- Give every ordinal its own 10 GiB `local-path` RWO PVC through
  `volumeClaimTemplates`; do not share a writable Hugging Face cache.
- Retain per-ordinal PVCs on scale-in. They survive pod replacement on the same
  VM but not VM destruction.
- Start Phase 4A with one warm replica and a trimmed Prometheus stack.
- Prove live series and PromQL behavior before installing KEDA.
- In the later KEDA gate, scale the StatefulSet as a complete unit from one to
  two replicas. Keep `minReplicaCount=1` and `maxReplicaCount=2`.
- Keep scale-to-zero separate because vLLM metrics disappear with the last pod;
  that topology requires a durable HTTP interceptor.

## Alternatives considered

### Deployment with one shared writable PVC

ReadWriteOnce constrains a volume to one node rather than necessarily one pod,
so two same-node pods may technically mount it. It was rejected because
concurrent cache downloads and locks create avoidable coupling, and the design
would not transfer cleanly to multiple nodes.

### Deployment with `emptyDir` caches

This is simple and gives each pod isolation, but every restart and scale-out
would redownload the model. That increases cold-start time, bandwidth, and
failure exposure.

### RWX network storage

This is the production-shaped shared-cache option, but it adds a storage system
that the single-node Vast lab does not provide. It is unnecessary for a 1.5B
acceptance model and would obscure the autoscaling experiment.

### TP=2 across both GPUs

TP=2 creates one sharded replica and consumes both GPUs, leaving no GPU for a
second replica. That proves model fit, not horizontal request-capacity scaling.

### Install Prometheus and KEDA together

Rejected because the scaler query must be based on series observed from the
pinned live stack, not copied from a different vLLM version or guessed from a
raw `/metrics` response.

## Evidence

- Phase 3 proved a `local-path` cache survives pod replacement on one k3s VM and
  is deleted with the VM.
- The Phase 4 preflight discovered two independent 16 GiB GPUs, 117 GiB free
  disk, and 24.5 GiB guest RAM.
- KEDA 2.20 supports StatefulSet targets through the Kubernetes scale
  subresource.
- vLLM 0.27.1 exports running, waiting, KV-cache, token, TTFT, and end-to-end
  latency series. Phase 4A proved Prometheus scrape labels, token totals, and
  waiting/running gauges. Histogram p95 queries are observability validation
  only; a short-window TTFT p95 that exceeded E2E p95 was a sparse-quantile
  artifact, not a latency ranking. See the Phase 4A status report.

## Consequences

- Scale-out ordinal 1 pays its own first-download cold start but later restarts
  reuse its cache.
- Disk use grows per replica, while replicas avoid a shared writable cache.
- StatefulSet startup ordering may lengthen scale-out; measure it rather than
  assuming Deployment-like behavior.
- Prometheus is capped and trimmed for the constrained host. Grafana,
  Alertmanager, and broad default rules are not part of Phase 4A.
- Phase 4B proved KEDA 1→2→1 on this StatefulSet. Phase 4C uses a durable
  HTTP interceptor for lab scale-to-zero; production TLS/HA remain future goals.
