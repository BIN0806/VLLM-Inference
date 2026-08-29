# Phase 4B status: KEDA 1→2→1 on the vLLM StatefulSet

Sanitized closeout for the horizontal scaling gate. No IP addresses, SSH
ports, host keys, tokens, credentials, instance IDs, kubeconfigs, or raw
cluster dumps are recorded here.

**Gate decision: GO for Phase 4B (KEDA 1→2→1 and ClusterIP load-distribution).**
**STOP before scale-to-zero, the HTTP interceptor, 9B, merge, and VM destroy.**

Access stayed SSH plus `kubectl port-forward` to loopback for the first KEDA
burst. A later addendum used an **in-cluster** client against the ClusterIP
Service. Inference and Prometheus Services stayed ClusterIP. kube-apiserver
remained firewalled to loopback and cluster-internal ranges and was not
published on the public interface. The KEDA HTTP add-on was **not** installed.

## Hardware and software (same VM as Phase 4A)

| Item | Recorded value |
|---|---|
| Host class | Vast Ubuntu KVM VM, 10 vCPUs, 24.51 GiB RAM, 125.81 GiB disk |
| GPU | 2× NVIDIA RTX A4000, 16376 MiB, driver 580.95.05 |
| k3s | `v1.34.10+k3s1` |
| kube-prometheus-stack | chart `88.6.0` |
| KEDA | Helm chart `keda-2.20.2`, app `2.20.2` |
| KEDA images | `ghcr.io/kedacore/keda:2.20.2`, `keda-metrics-apiserver:2.20.2`, `keda-admission-webhooks:2.20.2` |
| HTTP add-on | not installed (no chart, no HTTPScaledObject CRD) |
| Workload | StatefulSet `vllm` in namespace `inference`, TP=1, 1 GPU/pod, `max_num_seqs=2` |
| Model | `Qwen/Qwen2.5-1.5B-Instruct-AWQ` @ `3ecffa0ceb27851800f45519bab9c457a04405e1` |

The Phase 3 72.5 GiB disk exception was not used. Two replicas stayed inside
the 7 GiB memory limit per pod and left tens of GiB free on disk.

## Manual second-replica gate (before KEDA)

Began at **exactly one** Ready replica (`vllm-0` on host GPU 0). Scaled the
StatefulSet with `kubectl scale --replicas=2`.

| Check | Result |
|---|---|
| `vllm-1` GPU | Host GPU 1 (UUID distinct from GPU 0). Inside the container CUDA index is 0 because the NVIDIA runtime remaps the assigned device. |
| Ordinal PVC | `model-cache-vllm-1` Bound on a **different** volume from `model-cache-vllm-0` (10Gi `local-path` RWO) |
| Cold start | Scale command → Ready **178 s**. Container start → Ready **172 s**. Image already local; first download into an empty PVC. |
| Ready endpoints | Two addresses on `vllm`, `vllm-headless`, and `vllm-metrics` |
| Prometheus targets | `job=vllm-metrics` health **up** for both `vllm-0` and `vllm-1` |
| Both serve | Direct localhost completions HTTP 200 on each pod. In-cluster ClusterIP 24/24 HTTP 200. After scrape: `vllm:request_success_total` **190** on `vllm-0` and **13** on `vllm-1`. |
| Two-replica safety | MemAvailable **15.27 GiB** of 24.51; disk **41.01 used / 84.78 free**; cgroup RSS `vllm-0` **3.58 GiB**, `vllm-1` **5.55 GiB** (fresh download page cache); GPU0 **14171 MiB**, GPU1 **14168 MiB** |
| Scale back to 1 | `vllm-1` deleted; GPU 1 **0 MiB**; `model-cache-vllm-1` **still Bound** on the same volume; `vllm-0` Ready with 0 restarts |

`kubectl port-forward` to the ClusterIP Service pinned to one endpoint. That is
not Service load-balancing. Per-replica proof used in-cluster DNS (ClusterIP
and headless).

## KEDA install and ScaledObject

Installed **only** `kedacore/keda` **2.20.2** into namespace `keda`. Helm
releases after install: `keda-2.20.2` and `kube-prometheus-stack-88.6.0`. No
HTTP add-on.

The operator and admission webhook each restarted once during first
certificate injection, then stayed Ready. The metrics APIService
`v1beta1.external.metrics.k8s.io` became Available.

Applied `infra/keda/scaledobject-vllm.yaml` while the StatefulSet was still
**replicas=1**:

- `scaleTargetRef.apiVersion: apps/v1`, `kind: StatefulSet`, `name: vllm`
- `minReplicaCount: 1`, `maxReplicaCount: 2`
- Prometheus query `sum(vllm:num_requests_waiting)` (one scalar)
- `metricType: Value` (cluster-wide queue depth; **not** `AverageValue`)
- `threshold: "1"` so desired replicas = ceil(waiting / 1), clamped to 1..2
- `ignoreNullValues: "false"`
- HPA `scaleDown.stabilizationWindowSeconds: 300`
- No `activationThreshold` (irrelevant while min replicas is 1)

KEDA created HPA `keda-hpa-vllm` targeting `StatefulSet/vllm`. Idle HPA
targets were **0/1**. The external metric `s0-prometheus` returned **0**.
ScaledObject Ready=True, Active=False. Replica count stayed 1.

`pollingInterval: 15` is recorded on the ScaledObject but KEDA logs that it
is unused while `minReplicaCount=1`. The generated HPA drives 1→N.

## Automatic 1→2 (sticky port-forward test)

This first automatic scale-out used eight concurrent streaming clients through
the SSH tunnel and `kubectl port-forward` to the ClusterIP Service. That
forwarder pins a single backend. It proved KEDA 1→2 and client latency on one
path. It did **not** prove ClusterIP load-distribution. Began at exactly one
Ready replica. Prometheus recorded a sustained **waiting=6, running=2** queue
(`max_num_seqs=2` on one replica).

| Instant (UTC) | Event |
|---|---|
| 01:44:07 | Load start; HPA still 0/1, replicas=1 |
| 01:44:18 | Prometheus waiting=6; `vllm-1` created (warm PVC) |
| 01:44:20 | HPA metric=6, desired=2; STS spec=2; container started |
| 01:46:41 | `vllm-1` Ready; cache marker `phase4b-ordinal1-cache` present; hub snapshot present |

| Latency | Seconds |
|---|---|
| Detection (load start → STS spec=2 / pod create) | **11 s** |
| Pod create → container start | **2 s** |
| Container start → Ready (warm) | **141 s** |
| Create → Ready | **143 s** |
| Total scale-out (load start → Ready) | **154 s** |
| Prior cold container start → Ready | **172 s** |
| Warm vs cold Ready delta | **31 s faster** (engine load still dominates; HF download skipped) |

ScaledObject became Active=True. Both GPUs allocated (~14.2 GiB each). Both
`vllm-metrics` targets **up**. `vllm-0` stayed Ready with 0 restarts through
scale-out.

Requests kept running through scale-out. Client totals: **193 success, 0
errors, 0 timeouts**. Client-side TTFT p50/p95 **6.85 / 7.32 s**; E2E p50/p95
**9.15 / 9.71 s**. Those are same-request measurements, not histogram-quantile
rankings. The tunnel stayed pinned to `vllm-0`, so Prometheus
`generation_tokens_total` on `vllm-1` did not move during that burst. After
Ready, an in-cluster headless request to `vllm-1` returned HTTP 200. Headless
DNS is a liveness probe, not a ClusterIP distribution test.

## ClusterIP load-distribution addendum

A second 1→2→1 used only an in-cluster Job. The Job targeted
`http://vllm.inference.svc.cluster.local:8000` (the ClusterIP Service named
`vllm`). It did **not** use the headless Service and did **not** use
`kubectl port-forward`. Ten worker threads opened a **new TCP connection per
request** with `Connection: close`. The generator used the already-local vLLM
image with **no GPU** request. The Job and its ConfigMap were deleted
afterward; KEDA, Prometheus, and the StatefulSet were left in place.

Baseline before this Job (`vllm-0` only): `request_success_total` 389,
prompt tokens 17075, generation tokens 106510. HPA 0/1. GPU 1 idle. Ordinal-1
PVC still Bound.

| Instant (UTC) | Event |
|---|---|
| 02:25:42 | Job applied; one Ready replica |
| 02:25:52 / 02:25:53 | `vllm-1` created / container started (warm PVC) |
| 02:26:00 | Prom waiting=8 running=2; HPA metric=8 desired=2; STS spec=2 |
| 02:28:12 | `vllm-1` Ready (warm start **139 s** after container start) |
| 02:28:24 | First `vllm-1` successes (3); both scrape targets up |
| 02:30:25 | Load stopped after **133 s** post-Ready (Job delete) |
| 02:31:14 | Queue drained; waiting=0 running=0 |
| 02:36:01 | Automatic 2→1 (~287 s after metric 0) |

### Per-pod counters (Prometheus)

Windows use 15 s scrapes. Pre-Ready is 02:26:00→02:28:12 (**132 s**).
Post-Ready-while-loaded is 02:28:12→02:30:25 (**133 s**).

| Series | Pre-Ready Δ (`vllm-0` only) | Post-Ready Δ `vllm-0` | Post-Ready Δ `vllm-1` |
|---|---|---|---|
| `request_success_total` | +136 | **+148** | **+122** |
| `prompt_tokens_total` | +6800 | +7400 | +6200 |
| `generation_tokens_total` | +51558 | +56684 | +46793 |

Post-Ready successes split **55% / 45%** (`vllm-0` / `vllm-1`). Both replicas
processed a meaningful share of ClusterIP traffic. Running sat at 2+2 and
waiting split across pods (often 4–7 on ordinal 0 and 0–4 on ordinal 1).

Drain after Job delete (02:30:25→02:31:14) added more completions (`vllm-0`
737, `vllm-1` 162). That tail is in-flight work, not extra offered load.

### Aggregate capacity

| Window | Successful req/s | Generation tok/s |
|---|---|---|
| One replica, queued (pre-Ready) | **1.03** | **391** |
| Two Ready replicas, still queued (post-Ready) | **2.03** | **778** |

Throughput **about doubled** (1.97× requests, 1.99× generation tokens) once
ordinal 1 was Ready. ClusterIP capacity improved. The sticky port-forward test
could not show that.

### Client vs Prometheus latency

The Job printed per-request JSONL to stdout. Deleting the Job dropped those
container logs before a summary could be copied. Do not invent client
error/timeout counts.

Server-side, `increase(...[10m])` over this addendum: histogram `_count`
about **524** TTFT / **520** E2E, `_sum` 2257 s / 3176 s. Mean TTFT **4.30 s**,
mean E2E **6.10 s**. 10m `histogram_quantile` p95 TTFT **7.26 s**, E2E
**9.62 s**. Those two p95s sit on a dense sample and are ordered TTFT < E2E.
They remain **observability validation**, not an SLO. A short-window TTFT p95
that exceeds E2E p95 is not a valid latency comparison (Phase 4A).

### Host envelope while both replicas were Ready (idle after drain)

GPU 0 **14171 MiB**, GPU 1 **14168 MiB**. MemAvailable **15.14 GiB** of 24.51.
cgroup RSS `vllm-0` **3.59 GiB**, `vllm-1` **3.96 GiB**. Disk 41.63 used /
84.16 free.

After automatic scale-down: `vllm-0` Ready, 0 restarts; `vllm-1` absent;
`model-cache-vllm-1` Bound on the same volume; GPU 1 **0 MiB**; MemAvailable
**18.54 GiB**. Load-generator Job, Pod, and ConfigMap **removed**. ScaledObject
and HPA left in place.

## Automatic 2→1

Load ended 01:47:46. HPA metric returned to **0** by 01:47:52. The StatefulSet
stayed at 2 replicas through the **300 s** scale-down window, then scaled to
**1** at **01:52:39** (~287 s after the metric hit 0).

After scale-down:

- `vllm-0` Ready, 0 restarts
- `vllm-1` absent
- `model-cache-vllm-1` still Bound on the same volume
- GPU 1 **0 MiB**; GPU 0 still ~14.2 GiB
- MemAvailable **18.46 GiB**; disk **41.44 used / 84.36 free**

## Resource envelope (two replicas)

Caches, images, logs, and user files were not deleted to recover space.

| Stage | MemAvailable | Disk used / free | Note |
|---|---|---|---|
| One replica (4A closeout) | ~19.0 GiB | 39.31 / 86.48 GiB | GPU1 idle |
| Manual two replicas | 15.27 GiB | 41.01 / 84.78 GiB | Both GPUs ~14.2 GiB |
| KEDA two replicas (idle after load) | 15.07 GiB | 41.62 / 84.17 GiB | cgroup `vllm-0` 3.58 GiB, `vllm-1` 4.05 GiB |
| After auto scale-down | 18.46 GiB | 41.44 / 84.36 GiB | GPU1 idle; ordinal-1 PVC retained |

Two replicas did **not** exceed the 7 GiB pod memory limit, the 16 GiB host RAM
floor, or remaining disk.

## Not tested

- **Scale-to-zero** / `minReplicaCount: 0`
- **KEDA HTTP add-on** / interceptor
- **9B**, Ray, KubeRay, multi-node
- Production TLS, Ingress, NodePort, LoadBalancer
- Merging the draft PR
- Destroying the Vast VM (PVCs die with the VM)
