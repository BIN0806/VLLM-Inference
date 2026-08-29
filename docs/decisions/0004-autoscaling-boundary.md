# ADR 0004: Autoscaling boundary

## Status

Accepted for Phase 0. Phase 4B installed KEDA 2.20.2 and proved 1→2→1 on
waiting-queue depth. Phase 4C installed HTTP Add-on 0.15.0 for a single-node
lab scale-to-zero path. Production TLS/HA remain future goals.

## Decision

Autoscaling adds or removes **complete model replicas**. It never scales individual tensor-parallel or pipeline-parallel ranks, and it never scales Ray workers independently of the replica they belong to.

First Kubernetes MVP: `k8s-replica` with `minReplicaCount: 1` (one warm replica). Scale primarily on waiting work or gateway concurrency, not solely on running requests.

Scale-to-zero uses a durable HTTP front door. vLLM metrics cannot wake a
zero-replica service. Phase 4C uses KEDA HTTP Add-on 0.15.0
(`InterceptorRoute` + external-push ScaledObject) on the existing
StatefulSet. The `k8s-replica-zero` compute profile is documentation; the
renderer still refuses to emit a zero-replica workload YAML.

Combining KEDA with complete multi-node Ray replicas needs a later controller and is out of MVP.

## Consequences

Phase 0 records the boundary. Phase 4B proved KEDA 1→2→1 on aggregated
waiting depth with min replicas 1. Phase 4C is a single-node lab validation
of interceptor-held scale-from-zero, not production serverless inference.
