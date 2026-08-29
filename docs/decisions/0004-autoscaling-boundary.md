# ADR 0004: Autoscaling boundary

## Status

Accepted for Phase 0. Phase 4B installed KEDA 2.20.2 and proved 1→2→1 on
waiting-queue depth. Scale-to-zero stays later.

## Decision

Autoscaling adds or removes **complete model replicas**. It never scales individual tensor-parallel or pipeline-parallel ranks, and it never scales Ray workers independently of the replica they belong to.

First Kubernetes MVP: `k8s-replica` with `minReplicaCount: 1` (one warm replica). Scale primarily on waiting work or gateway concurrency, not solely on running requests.

Scale-to-zero is a later profile (`k8s-replica-zero`). vLLM metrics cannot wake a zero-replica service. A durable HTTP front door (KEDA HTTP Add-on interceptor or an explicitly approved equivalent) is mandatory for that profile.

Combining KEDA with complete multi-node Ray replicas needs a later controller and is out of MVP.

## Consequences

Phase 0 records the boundary. Phase 4B proved KEDA 1→2→1 on aggregated
waiting depth with min replicas 1. Do not attempt scale-to-zero until a
durable HTTP interceptor is approved.
