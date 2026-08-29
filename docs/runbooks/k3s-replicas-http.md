# Phase 4C: HTTP interceptor scale-to-zero (single-node lab)

> Historical/reproducibility procedure for the accepted Phase 4C gate. The
> project was later merged, Compose-validated, and torn down. HTTP 0→2
> remains untested. See [Final project status](../project-status.md).

Single-node k3s, two GPUs, 1.5B AWQ StatefulSet. Install **KEDA HTTP Add-on
0.15.0**, replace the Phase 4B Prometheus ScaledObject, and prove 1→0→1→0
through the interceptor.

Access is SSH plus `kubectl port-forward` to loopback. Do not publish
Ingress, NodePort, LoadBalancer, or a public HTTP URL. Do not deploy 9B.
This gate does not destroy the VM or merge `phase-4`. Those are a later
operator closeout: [vast-rental-closeout.md](vast-rental-closeout.md).

Live sanitized 4C closeout:
[k3s-replicas-http-status.md](k3s-replicas-http-status.md).
Compose 1.5B validation (after k3s stop):
[compose-1.5b-status.md](compose-1.5b-status.md).

## Pins

| Component | Pin | Source |
|---|---|---|
| KEDA | `2.20.2` | already installed |
| KEDA HTTP Add-on chart | `0.15.0` | `kedacore/keda-add-ons-http` |
| API | `http.keda.sh/v1beta1` `InterceptorRoute` | not `HTTPScaledObject` |
| ScaledObject | `infra/keda/scaledobject-vllm.yaml` | `external-push` |
| Historical 4B SO | `infra/keda/scaledobject-vllm-prometheus.yaml` | do not apply with the HTTP SO |
| Helm values | `infra/keda/http-add-on-values.yaml` | watch `inference`, 1 interceptor replica |

## Architecture

```text
client (SSH + kubectl port-forward)
        |
        v
ClusterIP keda-add-ons-http-interceptor-proxy:8080  (durable, min=1)
        |
        v
ClusterIP svc/vllm:8000
        |
        v
StatefulSet vllm  (KEDA min=0, max=2; ordinal PVCs retained)
```

Scale signal: interceptor concurrency via the HTTP external scaler, with
`metadata.interceptorRoute: vllm`. Prometheus/`vllm:*` cannot activate zero
replicas.

Timeouts (longer than observed 139–172 s vLLM startup):

| Budget | Value |
|---|---|
| Readiness (hold until backend Ready) | 240s |
| Total request | 420s |
| Response header (after send; excludes cold-start wait) | 300s |
| Client timeout | must exceed 420s (use ≥480s) |

Do not configure a cold-start placeholder. The original held request must
wait and return HTTP 200.

## Offline before apply

From the authoring workstation (no cluster mutation):

```bash
make phase4c-acceptance
```

That runs unit, schema, security, and repository-guard tests, then
`helm template` of chart **0.15.0** with `http-add-on-values.yaml` when Helm
is available.

Confirm application YAML:

- `kind: InterceptorRoute`, `apiVersion: http.keda.sh/v1beta1`
- live ScaledObject `type: external-push`, `minReplicaCount: 0`, `maxReplicaCount: 2`
- no `kind: HTTPScaledObject` in `infra/keda/`
- historical Prometheus ScaledObject still present and **not** the live file

## Constrained-host install

Install into namespace `keda`. Do not create a second KEDA namespace. Do not
install Grafana or an ingress controller.

```bash
helm repo add kedacore https://kedacore.github.io/charts
helm repo update
helm upgrade --install http-add-on kedacore/keda-add-ons-http \
  --version 0.15.0 \
  --namespace keda \
  --values infra/keda/http-add-on-values.yaml \
  --wait --timeout 10m
```

Record operator, scaler, and interceptor image tags **and** repo-digest
IDs from the Running pods.

Verify CRDs `interceptorroutes.http.keda.sh` (and the deprecated
HTTPScaledObject CRD the chart still installs — do not create those
objects). Verify operator, scaler, interceptor, and Services Ready.

```bash
kubectl apply -f infra/keda/interceptorroute-vllm.yaml
kubectl apply -f infra/keda/servicemonitor-http-addon.yaml
```

Prove a **warm** streaming request through the interceptor while the
StatefulSet is still at one replica and the Prometheus ScaledObject is
still live. Expect HTTP 200, non-empty SSE, `[DONE]`.

## Replace the ScaledObject

Only after the warm interceptor path works:

```bash
kubectl -n inference delete scaledobject vllm
kubectl apply -f infra/keda/scaledobject-vllm.yaml
```

Do **not** apply `scaledobject-vllm-prometheus.yaml` at the same time.

Verify **exactly one** HPA whose scale target is `StatefulSet/vllm`. The
HTTP add-on chart also creates a ScaledObject for the interceptor
Deployment; that HPA is a different target and must stay at 1 replica.

## Acceptance (lab)

1. Begin with one healthy replica.
2. Warm streaming request through the interceptor: HTTP 200, non-empty SSE, `[DONE]`.
3. Stop all **direct** client traffic to `svc/vllm`.
4. Wait for automatic 1→0.
5. Verify: desired/ready replicas 0; both GPUs idle; both PVCs Bound;
   vLLM endpoints and live `vllm:*` series gone; interceptor, HTTP scaler,
   KEDA, and Prometheus still alive.
6. Send **exactly one** streaming request through the interceptor at zero
   replicas. Do **not** retry it in the client.
7. Capture arrival, interceptor concurrency, ScaledObject/HPA activation,
   StatefulSet 0→1, pod create, container start, Ready, first-token,
   completion, and `X-KEDA-HTTP-Cold-Start`.
8. The original held request must return HTTP 200, valid SSE, non-empty
   output, and `[DONE]` without 502/504.
9. Prove ordinal-0 PVC / model cache reuse.
10. Record host RAM, disk, pod RSS, GPU memory, and interceptor resource use.
11. After completion, prove automatic 1→0 again and GPU idle.
12. Confirm vLLM metrics disappear again while interceptor/scaler metrics
    remain.

## Out of scope (STOP)

- Production TLS, interceptor HA, Ingress, NodePort, LoadBalancer
- `Qwen/Qwen3.5-9B`
- Merging `phase-4`
- Destroying the VM
- Claiming production serverless inference
