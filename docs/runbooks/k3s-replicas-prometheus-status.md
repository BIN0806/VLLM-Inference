# Phase 4A status: StatefulSet replica + Prometheus scrape

> Historical gate snapshot. Its “not tested” list is scoped to Phase 4A.
> Phase 4B later proved 1→2→1 and Phase 4C proved 0→1→0. See
> [Final project status](../project-status.md).

Sanitized closeout for the Prometheus observability gate. No IP addresses, SSH
ports, host keys, tokens, credentials, instance IDs, kubeconfigs, or raw
cluster dumps are recorded here.

**Gate decision: GO for Phase 4A (one 1.5B AWQ replica on two-GPU k3s, Prometheus scrape).**
**STOP before a second replica, KEDA, 9B, scale-to-zero, merge, and VM destroy.**

Access was SSH plus `kubectl port-forward` to loopback only. Inference and
Prometheus Services stayed ClusterIP. No public inference or metrics URL was
opened. kube-apiserver was firewalled to loopback and cluster-internal ranges
and was **not** published on the public interface. That is a host firewall,
not a Kubernetes Service type.

## Hardware and software versions

| Item | Recorded value |
|---|---|
| Host class | Vast Ubuntu KVM VM (`systemd-detect-virt=kvm`), not a Jupyter/container rental |
| OS | Ubuntu 22.04.5 LTS |
| Kernel | 6.8.0-59-generic |
| CPU | 10 vCPUs, Intel Core i9-9960X, one NUMA node |
| Guest RAM | 24.51 GiB (16 GiB floor met; 32 GiB preferred not met) |
| GPU | 2× NVIDIA RTX A4000, 16376 MiB each, compute 8.6, PCIe PHB |
| NVIDIA driver | 580.95.05 (`nvidia-smi` CUDA 13.0) |
| NVIDIA Container Toolkit | `1.18.0-1` (nvidia-ctk 1.18.0). Installed for k3s; `nvidia-ctk runtime configure` was **not** run against the k3s containerd template |
| Docker | Present on the host; k3s uses **embedded containerd**, not Docker |
| k3s | `v1.34.10+k3s1` (commit `39a4509e`), Kubernetes v1.34.10 |
| k3s linux/amd64 sha256 | `e63a3511b2603fd1436a1ea8d228348a3b47334b45024801d41a8c0e2d22e8c4` |
| containerd | `containerd://2.2.5-k3s2` |
| Helm | `v3.16.4` |
| kube-prometheus-stack | chart `88.6.0` (Prometheus Operator app v0.93.1, Prometheus v3.14.0) |
| NVIDIA device plugin | `nvcr.io/nvidia/k8s-device-plugin:v0.20.0` |
| RuntimeClass | `nvidia` (k3s auto-created; StatefulSet and device plugin set `runtimeClassName: nvidia`) |
| `nvidia.com/gpu` | capacity 2, allocatable 2 |
| vLLM image | `vllm/vllm-openai:v0.27.1@sha256:c2f3b1b964e47809b722b5e75b61b1e7b39a50f70388cf2bf2418f16a9f31da2` |
| Model | `Qwen/Qwen2.5-1.5B-Instruct-AWQ` revision `3ecffa0ceb27851800f45519bab9c457a04405e1` |
| Served name | `qwen2.5-1.5b-instruct-awq` |
| Topology | StatefulSet `vllm`, TP=1, PP=1, `distributed_executor_backend=mp`, `nvidia.com/gpu: 1` per pod, `replicas: 1` |
| Serving | `gpu_memory_utilization=0.9`, `max_model_len=8192`, `max_num_seqs=2`, AWQ, `/dev/shm` 2 GiB |
| Resources | request 2 CPU / 4 GiB; limit 4 CPU / 7 GiB |

The Phase 3 72.5 GiB disk exception was **not** used. This filesystem is 125.81
GiB total. Host RAM is a WARN versus the 32 GiB preference and a PASS versus
the 16 GiB floor.

## Disk and RAM (this host)

Caches, images, logs, and user files were **not** deleted to recover space.

| Stage | Used GiB | Free GiB | RAM note |
|---|---|---|---|
| Before install | 7.02 | 118.77 | MemAvailable ~23.8 GiB of 24.51 |
| After image pull / Ready replica / Prometheus | 39.31 | 86.48 | MemAvailable ~19.0 GiB; vLLM RSS 3.64 GiB; Prometheus RSS 35 MiB |

Closeout snapshot while still serving one replica: GPU 0 **14168** MiB of
16376 MiB, GPU 1 **0** MiB, load average 0.23 on 10 vCPUs. Prometheus
container limit remained 2 GiB; observed RSS was 35 MiB.

## k3s, NVIDIA, and kube-apiserver access

`/etc/rancher/k3s/config.yaml` (no kubeconfig contents):

```yaml
write-kubeconfig-mode: "600"
disable:
  - traefik
  - servicelb
nvidia-container-runtime-endpoint: /usr/bin/nvidia-container-runtime
```

Install used `https://get.k3s.io` with `INSTALL_K3S_VERSION=v1.34.10+k3s1`.
The k3s binary sha256 matched `configs/pins.yaml`. kubeconfig mode is `600`.

Do **not** run `nvidia-ctk runtime configure` against
`/var/lib/rancher/k3s/agent/etc/containerd/config.toml.tmpl`. Generated
containerd config registered BinaryName `/usr/bin/nvidia-container-runtime`.

Applying the overlay device-plugin YAML as a standalone object is **not** a
strategic merge. The first apply replaced the DaemonSet spec and failed.
Recovery: delete the DaemonSet, re-apply the pinned NVIDIA manifest, then
JSON-patch `runtimeClassName: nvidia`. After that, `nvidia.com/gpu` became 2.

kube-apiserver listens on the node and was restricted with host firewall
rules allowing loopback and cluster CIDRs (`10.42.0.0/16`, `10.43.0.0/16`)
and dropping other access to port 6443. That is a host firewall, not a
Kubernetes Service type. Application access stayed SSH-tunneled loopback.

## Workload shape

- StatefulSet `vllm`, `replicas: 1`, `RollingUpdate`, `OrderedReady`
- `enableServiceLinks: false`
- ClusterIP Services: `vllm` (inference), `vllm-headless`, `vllm-metrics`
- ServiceMonitor on `/metrics` every 15s, selecting `vllm-metrics`
- Per-replica PVC `model-cache-vllm-0`: **10Gi**, StorageClass **`local-path`**,
  **ReadWriteOnce**, Bound
- No shared writable Hugging Face cache
- Grafana, Alertmanager, default Prometheus rules, kube-state-metrics, and
  node-exporter were disabled. No KEDA objects existed.

## Acceptance results

Live tests used SSH plus `kubectl port-forward` to `127.0.0.1` only.
`tests/integration/test_phase4.py` with `RUN_PHASE4=1` and
`INFERENCE_PROFILE=vast-k3s-replicas`: **6 passed** in about 18.3s.

| Check | Result |
|---|---|
| Startup / readiness / liveness `GET /health` | HTTP 200 |
| `GET /v1/models` | served id `qwen2.5-1.5b-instruct-awq` |
| `GET /metrics` | HTTP 200; required series present on the replica |
| Concurrent SSE streams | non-empty output and `data: [DONE]` |
| Prometheus target `job=vllm-metrics` | health **up** |
| Token totals under SSE load | `vllm:prompt_tokens_total` and `vllm:generation_tokens_total` increased |
| Waiting/running gauges | vLLM `/metrics` ran 0→2 running and 0→4 waiting; Prometheus later scraped 2 / 2 under a 22s sustained load (15s scrape interval misses short spikes) |
| Transport | loopback HTTP through SSH; no public API |

PVC restart: wrote marker `phase4a-pvc-survives` under the Hugging Face cache,
deleted `vllm-0`, waited Ready. The marker and
`models--Qwen--Qwen2.5-1.5B-Instruct-AWQ` survived on the **same** PVC volume.
The replacement pod became Ready in about two minutes (image already local).

## Latency histograms: do not compare the first p95 pair

After the first SSE tests, two independent `histogram_quantile(0.95, sum(rate(...[5m])))`
queries returned **TTFT p95 ≈ 2.29 s** and **E2E p95 ≈ 1.88 s**. Those two
numbers are not a valid latency comparison. TTFT cannot exceed end-to-end
latency for the same request. The inversion came from sparse, coarse histogram
buckets and `rate()` over a short window that did not share a stable sample
set.

Re-query on the same Prometheus, same functions, matching windows. Cumulative
counters at that later instant:

| Histogram | `_count` | `_sum` (seconds) |
|---|---|---|
| `vllm:time_to_first_token_seconds` | 152 | 85.07 |
| `vllm:e2e_request_latency_seconds` | 152 | 141.21 |

| Window | TTFT p95 | E2E p95 | Notes |
|---|---|---|---|
| `rate()[5m]` | NaN | NaN | Idle; no samples in the window. Same failure mode as the first pair. |
| `rate()[10m]` | 0.74 s | 0.99 s | Observability validation only |
| `rate()[1h]` | 1.07 s | 1.64 s | Observability validation only; 1h mean TTFT 0.58 s, E2E 0.94 s |

Both histograms used the same observation count (152). Over the 1h window the
ordering is physically consistent (TTFT < E2E). These quantiles still sit on
wide vLLM buckets (TTFT jumps 0.5 → 0.75 → 1.0 → 2.5 s; E2E jumps 0.8 → 1.0 →
1.5 → 2.0 s). Treat them as **scrape and PromQL validation**, not an SLO or a
cross-metric ranking from the first 5m pair.

Token totals recorded immediately after SSE tests (2736 prompt / 1280
generation) were on the first pod. The PVC restart reset those counters.
They prove scrape, not a lifetime total.

## PVC persistence scope

k3s `local-path` keeps each ordinal cache across **pod restarts on this VM**.
It is node-local disk, **not** provider-persistent storage. **Destroying the
Vast VM deletes the PVCs and the model caches.** Do not describe these volumes
as Vast persistent disks.

## Goals after the Phase 4A checkpoint

- Exercise the second replica (completed in Phase 4B).
- Add KEDA/HPA scaling (completed in Phase 4B).
- Add durable-front-door scale-to-zero (completed for 0→1→0 in Phase 4C).
- Exercise 9B horizontal replicas on GPUs with sufficient TP=1 headroom.
- Extend Ray/KubeRay across physical nodes.
- Add production TLS, Ingress, authentication, and high availability.
- Run a statistically valid latency/SLO study with a frozen workload.
