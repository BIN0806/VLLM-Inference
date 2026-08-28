# ADR 0004: Autoscaling boundary

## Status

Accepted for Phase 0. Not implemented. Phase 3 did not install Prometheus or KEDA. Phase 4 is the first planned autoscaling gate (Prometheus scrape, then KEDA 1→2). Scale-to-zero stays later.

## Decision

Autoscaling adds or removes **complete model replicas**. It never scales individual tensor-parallel or pipeline-parallel ranks, and it never scales Ray workers independently of the replica they belong to.

First Kubernetes MVP: `k8s-replica` with `minReplicaCount: 1` (one warm replica). Scale primarily on waiting work or gateway concurrency, not solely on running requests.

Scale-to-zero is a later profile (`k8s-replica-zero`). vLLM metrics cannot wake a zero-replica service. A durable HTTP front door (KEDA HTTP Add-on interceptor or an explicitly approved equivalent) is mandatory for that profile.

Combining KEDA with complete multi-node Ray replicas needs a later controller and is out of MVP.

## Consequences

Phase 0 records the boundary. Phase 3 deployed one k3s replica and did not
install Prometheus or KEDA. Those directories remain contracts until a later
approved gate.
