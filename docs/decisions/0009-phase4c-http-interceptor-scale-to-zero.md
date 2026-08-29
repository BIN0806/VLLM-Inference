# ADR 0009: HTTP interceptor for scale-to-zero

## Status

Accepted for Phase 4C as a **single-node lab** validation. Live evidence is in
[k3s-replicas-http-status.md](../runbooks/k3s-replicas-http-status.md).
The KEDA HTTP Add-on is beta. This decision does **not** claim production
serverless inference, public TLS, interceptor HA, or managed Kubernetes.

## Context

Phase 4B proved KEDA 1→2→1 on `sum(vllm:num_requests_waiting)` with
`minReplicaCount: 1`. That scaler can add a complete replica only while at
least one vLLM pod exists to emit Prometheus series. At zero replicas:

- `vllm:*` series disappear from scrape.
- A Prometheus query of waiting/running depth is empty or stale.
- No in-cluster HTTP listener remains on `svc/vllm` to observe a new request.

A client that talks directly to `svc/vllm` at zero replicas gets connection
failure, not a held request. Scale-from-zero therefore needs a **durable**
process that:

1. Stays scheduled while the StatefulSet is at 0.
2. Accepts HTTP and records concurrency.
3. Pushes that concurrency to KEDA so the HPA can activate 0→1.
4. Holds the original request until a Ready backend exists, within an
   explicit timeout longer than observed vLLM startup (139–172 s).

The current InterceptorRoute API is `http.keda.sh/v1beta1`. The former
`HTTPScaledObject` API is deprecated and must not be the live object.

## Decision

- Install pinned KEDA HTTP Add-on **0.15.0** into the existing `keda`
  namespace. Restrict the operator watch namespace to `inference`.
- Keep **one** interceptor replica (not the chart default of three) and cap
  operator, scaler, and interceptor memory for this ~24.5 GiB single-node lab.
- Route: client → interceptor ClusterIP → existing `svc/vllm` → StatefulSet.
- Access the interceptor only through SSH plus `kubectl port-forward`. No
  Ingress, NodePort, LoadBalancer, public HTTP, or public TLS.
- Declare routing with `InterceptorRoute` and scale with a separately
  managed KEDA `ScaledObject` (`type: external-push`) that sets
  `metadata.interceptorRoute` to the route name.
- StatefulSet bounds: `minReplicaCount: 0`, `maxReplicaCount: 2`. Preserve
  both ordinal PVCs on scale-in.
- Scale on interceptor **concurrency** with `targetValue: 1`.
- Timeouts: readiness ~240 s, request ~420 s, response-header ~300 s. The
  client timeout must exceed the 420 s request budget. Do not configure a
  cold-start placeholder that returns 503 while the backend is scaling.
- Preserve the Phase 4B Prometheus ScaledObject as historical YAML. Never
  run two ScaledObjects or HPAs against StatefulSet `vllm`. Replace the live
  Prometheus object with the HTTP object; the chart may still create a
  ScaledObject for the interceptor Deployment (a different target).
- Do not install Grafana, an ingress controller, or a second monitoring stack.
  Optionally scrape the add-on scaler `/metrics` on port 2223.

## Alternatives considered

- **Prometheus/vLLM metrics at min=0.** Rejected: series vanish with the last
  pod, so there is no activation signal.
- **Keep min=1 forever.** Rejected for this gate: Phase 4C exists to prove
  1→0→1 hold-and-wake, not to avoid it.
- **Deprecated `HTTPScaledObject`.** Rejected: 0.15 documents InterceptorRoute
  plus a separately managed ScaledObject as the current API.
- **Ingress / NodePort / LoadBalancer / public TLS.** Rejected: lab access
  stays SSH plus port-forward. Production TLS/HA are untested.
- **Three interceptor replicas (chart default).** Rejected on this host: one
  durable replica is enough for a single-node lab and keeps RAM headroom.
- **Immediate 503 placeholder during cold start.** Rejected: acceptance
  requires the original held request to return HTTP 200 and valid SSE.

## Evidence

Live closeout:
[k3s-replicas-http-status.md](../runbooks/k3s-replicas-http-status.md).

- Chart `keda-add-ons-http-0.15.0` in namespace `keda`; operator watch
  `inference`; one interceptor replica. Resolved digests are in
  `configs/pins.yaml`.
- Exactly one HPA targeted `StatefulSet/vllm` after the Prometheus
  ScaledObject was deleted. The chart HPA targets the interceptor Deployment.
- Warm interceptor SSE: HTTP 200, `X-KEDA-HTTP-Cold-Start: false`.
- Automatic 1→0 on ScaledObject replacement: STS 0/0, both GPUs idle, both
  PVCs Bound, live `vllm:*` empty.
- One no-retry cold-start: activation ~1 s, Ready 150 s, hold 152.4 s,
  HTTP 200, `X-KEDA-HTTP-Cold-Start: true`, `[DONE]`, marker
  `phase4c-ordinal0-cache` reused.
- Second automatic 1→0 ~327 s after completion. Scaler `/metrics` on 2223
  stayed up.

## Consequences

- 0→1 activation is owned by interceptor concurrency, not vLLM Prometheus.
- Cold start includes pod create, model load from the retained ordinal-0 PVC,
  and first-token time. Expect on the order of minutes, not milliseconds.
- The interceptor is a new failure domain. If it dies at zero replicas, no
  client can wake vLLM.
- HTTP Add-on is beta; this is a lab GO/NO-GO, not a production claim.
- Phase 4B waiting-queue 1→N remains the historical capacity scaler and is
  not live while the HTTP ScaledObject owns the StatefulSet.
