# Phase 4B status: KEDA 1→2→1 on the vLLM StatefulSet

Sanitized closeout for the horizontal scaling gate. No IP addresses, SSH
ports, host keys, tokens, credentials, instance IDs, kubeconfigs, or raw
cluster dumps are recorded here.

**Gate decision: GO for Phase 4B (manual second replica, then KEDA 1→2→1).**
**STOP before scale-to-zero, the HTTP interceptor, 9B, merge, and VM destroy.**

Access stayed SSH plus `kubectl port-forward` to loopback. Inference and
Prometheus Services stayed ClusterIP. kube-apiserver remained firewalled to
loopback and cluster-internal ranges and was not published on the public
interface. The KEDA HTTP add-on was **not** installed.

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

## Automatic 1→2

Began at exactly one Ready replica. Started eight concurrent streaming
clients through the SSH tunnel (`max_tokens=512`). Prometheus recorded a
sustained **waiting=6, running=2** queue (`max_num_seqs=2` on one replica).

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
Ready, an in-cluster headless request to `vllm-1` returned HTTP 200.

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
