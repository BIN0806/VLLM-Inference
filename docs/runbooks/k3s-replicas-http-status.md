# Phase 4C status: HTTP interceptor scale-to-zero (single-node lab)

> Accepted historical gate snapshot. The project was later merged and the VM
> destroyed. HTTP 0→2, public TLS, and interceptor HA remain untested. See
> [Final project status](../project-status.md).

Sanitized closeout for the lab scale-to-zero gate. No IP addresses, SSH
ports, host keys, tokens, credentials, instance IDs, kubeconfigs, or raw
cluster dumps are recorded here.

**Gate decision: GO for Phase 4C as a single-node lab validation.**
**STOP before production TLS/HA, public HTTP, interceptor HA, 9B, and HTTP 0→2.**

This gate used **one** interceptor replica. The KEDA HTTP Add-on is **beta**.
The interceptor stayed ClusterIP and was reached only through SSH plus
`kubectl port-forward`. kube-apiserver remained firewalled to loopback and
cluster-internal ranges. No Ingress, NodePort, LoadBalancer, or public TLS
was installed. This is **not** production serverless inference.

HTTP **0→2 was not tested**. Phase 4B proved Prometheus-driven **1→2**.
Phase 4C proved interceptor-driven **0→1** (and 1→0 twice).

## Hardware and software (same VM as Phase 4B)

| Item | Recorded value |
|---|---|
| Host class | Vast Ubuntu KVM VM, 10 vCPUs, 24.51 GiB RAM, 125.81 GiB disk |
| GPU | 2× NVIDIA RTX A4000, 16376 MiB, driver 580.95.05 |
| k3s | `v1.34.10+k3s1` |
| kube-prometheus-stack | chart `88.6.0` |
| KEDA | Helm chart `keda-2.20.2`, app `2.20.2` |
| HTTP Add-on | Helm chart `keda-add-ons-http-0.15.0`, app `0.15.0` |
| HTTP images | `http-add-on-operator:0.15.0@sha256:d579b952ff0a0c3046a49d0e066bc06d33d1944b5f89b5fac5145d89f9f78959` |
| | `http-add-on-scaler:0.15.0@sha256:f748178bc4af9e546d5da38c4e1b1d8d236a343bb30927b292131c6f4c978394` |
| | `http-add-on-interceptor:0.15.0@sha256:4e88e7808652e7c438f66d67bc8a53ce6261b6081c81475bd4758602460af499` |
| Operator watch | namespace `inference` only |
| Interceptor replicas | min=1, max=1 (not the chart default of 3) |
| Workload | StatefulSet `vllm` in namespace `inference`, TP=1, 1 GPU/pod |
| Model | `Qwen/Qwen2.5-1.5B-Instruct-AWQ` @ `3ecffa0ceb27851800f45519bab9c457a04405e1` |
| API | `http.keda.sh/v1beta1` `InterceptorRoute`; no `HTTPScaledObject` objects |

Phase 4B Prometheus ScaledObject YAML is kept as
`infra/keda/scaledobject-vllm-prometheus.yaml` and was **not** left live.

## Offline before apply

Authoring host rendered `kedacore/keda-add-ons-http` **0.15.0** with
`infra/keda/http-add-on-values.yaml`. The template installed CRDs (including
the deprecated HTTPScaledObject CRD), Deployments, Services, and one
ScaledObject for the interceptor Deployment. It did **not** create a
StatefulSet scaler and did **not** create `kind: HTTPScaledObject` objects.
Unit, schema, security, and repository-guard tests passed before the cluster
changed.

## Install and ScaledObject swap

Installed into the existing `keda` namespace. No Grafana, ingress controller,
or extra monitoring stack.

| Check | Result |
|---|---|
| Operator / scaler / interceptor | 1/1 Ready each |
| CRDs | `interceptorroutes.http.keda.sh` Ready; HTTPScaledObject CRD present unused |
| Services | ClusterIP only; proxy `keda-add-ons-http-interceptor-proxy:8080` |
| InterceptorRoute `vllm` | Ready; target `svc/vllm:8000`; concurrency target 1 |
| Timeouts | readiness 240s, request 420s, response-header 300s |
| HTTPScaledObject objects | **0** |
| Combined add-on RSS | interceptor 10.63 MiB, operator 12.75 MiB, scaler 16.86 MiB |

Warm streaming request through the interceptor **while one replica was still
Ready** and the Prometheus ScaledObject was still live: HTTP **200**,
`X-KEDA-HTTP-Cold-Start: false`, 11 SSE chunks, `[DONE]`, hold **0.207 s**.

Then deleted ScaledObject `vllm` and applied the HTTP `external-push` object
(`minReplicaCount: 0`, `maxReplicaCount: 2`,
`metadata.interceptorRoute: vllm`). After the swap:

| Owner | Target | Count |
|---|---|---|
| `keda-hpa-vllm` | `StatefulSet/vllm` | **exactly one** |
| `keda-hpa-keda-add-ons-http-interceptor` | interceptor Deployment | different target, stays at 1 |

KEDA HPA `minReplicas` remains 1 by design. 0↔1 is the ScaledObject
activation path (`KEDAScaleTargetActivated` /
`KEDAScaleTargetDeactivated`). HPA reports `<unknown>/1` while the
StatefulSet is at zero because HPA scaling is disabled at replica count 0.

## 1→0 after the swap

Replacing the live ScaledObject deactivated the StatefulSet from 1 to 0
within a few seconds (not the 300 s cooldown). That is automatic KEDA
deactivation of an idle min=0 object, not a second client request.

| Check at zero (02:53:56 UTC) | Result |
|---|---|
| StatefulSet desired/ready | **0/0** |
| GPU 0 / GPU 1 | **0 MiB / 0 MiB**, 0% util |
| PVCs `model-cache-vllm-0` and `-1` | both **Bound** on the same volumes |
| `svc/vllm` endpoints | none |
| Prometheus `up{job="vllm-metrics"}` | empty vector |
| Instant `count({__name__=~"vllm:.*"})` | empty vector |
| Interceptor, HTTP scaler, KEDA, Prometheus | all Ready |

## Cold-start hold (exactly one non-retried request)

One streaming `POST /v1/chat/completions` through the interceptor
port-forward. The request was **held through a 150-second model startup**
(create → Ready). Client timeout **480 s**. The client did **not** retry.

| Instant (UTC) | Event |
|---|---|
| 02:54:20.963 | Request arrival; ScaledObject already Active |
| 02:54:21 | Pod `vllm-0` created and scheduled |
| 02:54:23 | Container started (image already local) |
| 02:54:26 | STS desired=1; HPA current=1 |
| 02:56:51 | Pod Ready (**150 s** after create, **148 s** after start) |
| 02:56:53.345 | First token and completion |

| Measurement | Value |
|---|---|
| HTTP status | **200** (not 502/504) |
| `X-KEDA-HTTP-Cold-Start` | **true** |
| Hold / TTFT | **152.426 s** / **152.382 s** |
| SSE | valid event-stream; 11 chunks; non-empty output (34 chars); `[DONE]` |
| Activation trigger | `s0-http_vllm_concurrency` (`KEDAScaleTargetActivated` 0→1) |
| PVC reuse | marker `phase4c-ordinal0-cache` and hub dir `models--Qwen--Qwen2.5-1.5B-Instruct-AWQ` present |

Ready time matches a **warm PVC** start (Phase 4B cold empty PVC was 172 s;
warm ordinal-1 was 139–141 s). Weights were not re-downloaded.

## Envelope while the woken replica was Ready

| Resource | Value |
|---|---|
| MemAvailable | **18 GiB** of 24.51 |
| Disk | **42 GiB used / 85 GiB free** |
| vLLM cgroup RSS | **5.00 GiB** |
| GPU 0 / GPU 1 | **14168 MiB** / **0 MiB** |
| HTTP add-on RSS | ~40 MiB combined (see install table) |

## Second automatic 1→0

After the held request completed at 02:56:53, no further client traffic was
sent. ScaledObject Active became False immediately. STS returned to **0/0**
at **03:02:20**. That is the **normal** cooldown path: **approximately 327
seconds** (cooldownPeriod 300 plus scrape/reconcile), not a forced scale.

| Check after second 1→0 | Result |
|---|---|
| StatefulSet | 0/0 |
| Both GPUs | 0 MiB, 0% |
| Both PVCs | Bound |
| `up{job="vllm-metrics"}` and live `vllm:*` | empty |
| Scaler `/metrics` :2223 | HTTP 200, 10226 bytes |
| Prometheus target `keda-add-ons-http-external-scaler` | **up** |
| Interceptor / KEDA / Prometheus | Ready |
| MemAvailable | **21 GiB** |

## Goals after the Phase 4C checkpoint

- Exercise interceptor-driven **0→2**. Phase 4B completed Prometheus-driven
  **1→2** and Phase 4C completed interceptor-driven **0→1**.
- Add production TLS, authentication, Ingress, and interceptor HA.
- Run multiple interceptor replicas with failure testing.
- Autoscale independent `Qwen/Qwen3.5-9B` replicas on suitable GPUs.
- Deploy on managed/multi-node Kubernetes and extend Ray across physical nodes.
- Freeze a workload and evaluate the hardware needed for 5,000 output tokens/s.
