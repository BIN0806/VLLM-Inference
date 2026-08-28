# Phase 3 status: k3s 1.5B AWQ replica

Sanitized closeout for the first Kubernetes gate. No IP addresses, SSH
ports, host keys, tokens, credentials, instance IDs, kubeconfigs, or raw
cluster dumps are recorded here.

**Gate decision: GO for Phase 3 (1.5B AWQ on single-node k3s).**
**STOP before 9B, Ray, Prometheus, KEDA, and scale-to-zero.**

Access was SSH plus `kubectl port-forward` to loopback only. The Service
stayed ClusterIP. No public inference URL was opened.

## Hardware and software versions

| Item | Recorded value |
|---|---|
| Host class | Vast Ubuntu KVM VM (`systemd-detect-virt=kvm`), not a Jupyter/container rental |
| OS | Ubuntu 22.04.5 LTS |
| Kernel | 6.8.0-87-generic |
| CPU | 17 vCPUs, Intel Xeon E5-2696 v3 |
| Guest RAM | 49.25 GiB |
| GPU | 1× NVIDIA GeForce RTX 3090, 24576 MiB, compute 8.6 |
| NVIDIA driver | 580.105.08 (`nvidia-smi` CUDA 13.0) |
| NVIDIA Container Toolkit | 1.18.0 (present for Docker; unused by k3s) |
| Docker | 29.0.3 present; k3s uses **embedded containerd**, not Docker |
| k3s | `v1.34.10+k3s1` (commit `39a4509e`), Kubernetes v1.34.10 |
| k3s linux/amd64 sha256 | `e63a3511b2603fd1436a1ea8d228348a3b47334b45024801d41a8c0e2d22e8c4` |
| containerd | `containerd://2.2.5-k3s2` |
| NVIDIA device plugin | `nvcr.io/nvidia/k8s-device-plugin:v0.20.0` |
| RuntimeClass | `nvidia` (k3s auto-created; Deployment sets `runtimeClassName: nvidia`) |
| `nvidia.com/gpu` | capacity 1, allocatable 1 |
| vLLM image | `vllm/vllm-openai:v0.27.1@sha256:c2f3b1b964e47809b722b5e75b61b1e7b39a50f70388cf2bf2418f16a9f31da2` |
| Model | `Qwen/Qwen2.5-1.5B-Instruct-AWQ` revision `3ecffa0ceb27851800f45519bab9c457a04405e1` |
| Served name | `qwen2.5-1.5b-instruct-awq` |
| Topology | TP=1, PP=1, `distributed_executor_backend=mp`, `nvidia.com/gpu: 1` |
| Serving | `gpu_memory_utilization=0.9`, `max_model_len=8192`, `max_num_seqs=8`, AWQ |

## Disk-exception measurements

The general rental floor remains **≥80 GiB, preferably 100 GiB**. It was **not**
lowered. A narrow exception applied only to profile `vast-k3s-replica` and
model `qwen2.5-1.5b-instruct-awq` on this already-rented 72.5 GiB root
filesystem. See [ADR 0006](../decisions/0006-phase3-1.5b-disk-exception.md).

Floors: ≥40 GiB free before install; ≥15 GiB free after acceptance. Caches,
images, logs, and user files were **not** deleted to recover space.
`vast-k3s-replica-9b` stayed **NO-GO** and was not attempted.

Root filesystem totals were 72.5 GiB throughout (±0.0 GiB vs the recorded
exception). Measured used/free:

| Stage | Used GiB | Free GiB | Exception check |
|---|---|---|---|
| Before k3s / vLLM install | 17.47 | 55.02 | PASS (≥40 GiB free) |
| After vLLM image pull / first container start | 47.37 | 25.12 | — |
| After first pod Ready | 50.22 | 22.27 | — |
| After PVC restart and live acceptance | 50.39 | 22.1 | PASS (≥15 GiB free) |
| Closeout snapshot (still serving) | 51.52 | 20.97 | PASS (≥15 GiB free) |

After-acceptance host preflight: overall **WARN** (documented disk exception
vs the 80 GiB rental floor), `disk-free` **PASS**, `nvidia.com/gpu=1` **PASS**.

## k3s and NVIDIA runtime configuration

`/etc/rancher/k3s/config.yaml` (no kubeconfig contents):

```yaml
write-kubeconfig-mode: "600"
disable:
  - traefik
  - servicelb
nvidia-container-runtime-endpoint: /usr/bin/nvidia-container-runtime
```

Install used `https://get.k3s.io` with `INSTALL_K3S_VERSION=v1.34.10+k3s1`.
The k3s binary sha256 matched the pin in `configs/pins.yaml`.

Do **not** run `nvidia-ctk runtime configure` against
`/var/lib/rancher/k3s/agent/etc/containerd/config.toml.tmpl`. That overwrites
the k3s template and can break CNI. k3s registers NVIDIA when
`nvidia-container-runtime` is on PATH and the endpoint above is set.

k3s v1.34 kubelet device-plugin sockets are at `/var/lib/kubelet/device-plugins`
(the stock path). `/var/lib/rancher/k3s/agent/kubelet/device-plugins` does
**not** exist on this k3s and must not be patched in.

The GPU pod and the device-plugin DaemonSet set `runtimeClassName: nvidia`.
The vast-k3s overlay must set `namespace: inference` and a namespaced patch
target so the RuntimeClass patch applies to the Deployment.

kube-apiserver was firewalled to loopback and cluster-internal ranges. It
was not published on the public interface. Application access stayed
SSH-tunneled loopback.

## Kubernetes `VLLM_PORT` service-link collision

With the default `enableServiceLinks: true`, Kubernetes injects environment
variables from Services in the same namespace. The Service name `vllm`
injects `VLLM_PORT=tcp://<cluster-ip>:8000` (a URI, not an integer).

vLLM EngineCore then raises `ValueError: VLLM_PORT appears to be a URI` and
the replica crash-loops.

**Fix:** set `enableServiceLinks: false` on the pod spec (`src/inference_platform/k8s/render.py`,
`infra/kubernetes/base/deployment.yaml`). After that patch the pod became
Ready in about three minutes and live tests passed. Do not work around this
by publishing a NodePort or LoadBalancer.

## Acceptance results

Live tests used SSH plus `kubectl port-forward` to `127.0.0.1` only.
`tests/integration/test_phase3.py` with `RUN_PHASE3=1` and
`INFERENCE_PROFILE=vast-k3s-replica`: **3 passed** in about 6.65s.

| Check | Result |
|---|---|
| Startup / readiness / liveness `GET /health` | HTTP 200 |
| `GET /v1/models` | served id `qwen2.5-1.5b-instruct-awq` |
| `GET /metrics` | HTTP 200, non-empty body |
| Concurrent SSE streams | non-empty output and `data: [DONE]` |
| Transport | loopback HTTP through SSH; no public API |

PVC restart check: Hugging Face cache **1626099264 → 1626099282** bytes
(18-byte marker), **24 → 25** files. The marker survived. The replacement
pod became Ready in about three minutes (`Recreate` strategy,
`terminationGracePeriodSeconds: 60`).

Closeout snapshot while still serving: Deployment replicas=1, pod Running
and Ready, restartCount=0, cache **1626099282** bytes / **25** files, GPU
memory used **21961** MiB of 24576 MiB.

## PVC persistence scope

PVC `vllm-model-cache`: **40Gi**, StorageClass **`local-path`**,
**ReadWriteOnce**, Bound.

k3s `local-path` keeps the model cache across **pod restarts on this VM**.
It is node-local disk, **not** provider-persistent storage. **Destroying the
Vast VM deletes the PVC and the model cache.** Closeout will destroy that
VM after the merge, tag, and CI evidence are pushed. Do not describe this
volume as a Vast persistent disk or an attachable volume.

## Not tested

The following were **not tested** in Phase 3 and are **not claimed**:

- **9B** (`vast-k3s-replica-9b` / `Qwen/Qwen3.5-9B`) was not deployed and
  remains NO-GO on this filesystem.
- **Ray** (KubeRay, Ray executor, multi-node Ray) was not installed.
- **Prometheus** (kube-prometheus-stack or any scrape config) was not
  installed. `/metrics` was fetched from the vLLM process only.
- **KEDA** was not installed. Horizontal pod scaling was not demonstrated.
- **Scale-to-zero** and the KEDA HTTP interceptor were not installed or
  tested. `k8s-replica-zero` remains a later profile.

No monitoring, KEDA, or Ray namespaces were present at closeout. EKS, GKE,
and minikube are unvalidated.
