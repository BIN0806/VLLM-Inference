# Phase 4A: two-replica-capable k3s + Prometheus scrape

Single-node k3s, two schedulable NVIDIA GPUs, one warm **1.5B AWQ** vLLM
replica as a StatefulSet, Prometheus scrape of `/metrics`. Access is SSH plus
`kubectl port-forward` to loopback. Do not publish NodePort or a public HTTP
URL. Do not install KEDA. Do not scale to two replicas in this gate. Do not
deploy 9B.

Sanitized host facts belong in gitignored `docs/phase4-preflight.md`. Do not
commit IPs, SSH ports, instance IDs, kubeconfigs, or host keys.

## Pins

| Component | Pin | Source |
|---|---|---|
| k3s | `v1.34.10+k3s1` (same as Phase 3) | `configs/pins.yaml` |
| NVIDIA Container Toolkit | `1.18.0-1` | apt `nvidia-container-toolkit` |
| NVIDIA device plugin | `0.20.0` | [tag](https://github.com/NVIDIA/k8s-device-plugin/releases/tag/v0.20.0) |
| Helm | `v3.16.4` | `https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3` |
| kube-prometheus-stack | chart `88.6.0` | prometheus-community |
| vLLM image | digest in `configs/pins.yaml` | never `latest` |
| Model | `Qwen/Qwen2.5-1.5B-Instruct-AWQ` @ `3ecffa0ceb27851800f45519bab9c457a04405e1` | portable baseline |

Profile: `vast-k3s-replicas` (compute `k8s-replicas`). Overlay:
`infra/kubernetes/overlays/vast-k3s-replicas`. Prometheus values:
`infra/observability/kube-prometheus-stack-values.yaml`. PromQL contract:
`infra/observability/promql/vllm-acceptance.yaml`.

The Phase 3 72.5 GiB disk exception does **not** apply. Require the
`host_baseline` floors (≥80 GiB disk, preferably 100 GiB; ≥16 GiB RAM,
preferably 32 GiB). Cap Prometheus at 2 GiB RAM and `/dev/shm` at 2 GiB per
vLLM pod on ~24.5 GiB hosts.

## Offline (authoring Mac)

```bash
./scripts/phase4_acceptance.sh
make k8s-render-replicas
```

This does not talk to a cluster. Live GPU/PromQL tests need `RUN_PHASE4=1`
after the replica is Ready.

## Install order on the GPU VM

Do not run `nvidia-ctk runtime configure` against
`/var/lib/rancher/k3s/agent/etc/containerd/config.toml.tmpl`.

1. Recheck free disk and RAM still meet the gate.
2. Install pinned NVIDIA Container Toolkit `1.18.0-1`.
3. Write `/etc/rancher/k3s/config.yaml` (same as Phase 3):

   ```yaml
   write-kubeconfig-mode: "600"
   disable:
     - traefik
     - servicelb
   nvidia-container-runtime-endpoint: /usr/bin/nvidia-container-runtime
   ```

4. Install k3s `v1.34.10+k3s1` from `https://get.k3s.io`. Confirm the binary
   sha256 matches `configs/pins.yaml`. Restrict kube-apiserver to loopback and
   cluster CIDRs after install (do not leave 6443 open to the public
   interface).
5. Confirm `grep nvidia /var/lib/rancher/k3s/agent/etc/containerd/config.toml`
   and `kubectl get runtimeclass nvidia`.
6. Apply NVIDIA device plugin 0.20.0, then
   `infra/kubernetes/overlays/vast-k3s-replicas/nvidia-device-plugin-k3s-patch.yaml`.
   Confirm `nvidia.com/gpu: 2`.
7. Apply the StatefulSet overlay with **replicas=1**. Create
   `vllm-secrets` from `secret.yaml.example` if needed. Never commit tokens.
8. Install Helm `v3.16.4`. Add prometheus-community. Install
   kube-prometheus-stack `88.6.0` with the trimmed values file into namespace
   `monitoring`. Service type stays ClusterIP.
9. Apply `kustomization-monitoring.yaml` so Prometheus scrapes `vllm-metrics`.
10. Port-forward `svc/vllm` (8000) and `svc/prometheus-operated` or the chart
    Prometheus Service (9090) to `127.0.0.1` only. SSH-tunnel those loopbacks
    from the authoring Mac.

## Workload shape

- StatefulSet `vllm`, `replicas: 1`, `RollingUpdate`, `OrderedReady`
- `nvidia.com/gpu: 1` per pod, TP=1, PP=1, `mp`, no Ray
- `enableServiceLinks: false`
- Per-replica 10 GiB `local-path` RWO PVC via `volumeClaimTemplates`
- No shared writable Hugging Face cache
- Requests ≈ 2 CPU / 4 GiB; limits ≤ 4 CPU / 7 GiB; `/dev/shm` 2 GiB
- `max_model_len=8192`, `max_num_seqs=2`
- ClusterIP Services: `vllm` (inference), `vllm-headless`, `vllm-metrics`

k3s `local-path` PVCs persist across pod restarts on this VM. They **do not**
survive destruction of the Vast VM.

## Live acceptance

```bash
RUN_PHASE4=1 INFERENCE_PROFILE=vast-k3s-replicas \
  PROMETHEUS_BASE_URL=http://127.0.0.1:9090 \
  ./scripts/phase4_acceptance.sh
```

Prove:

- `/health`, `/v1/models`, SSE, `/metrics`
- Prometheus discovers and scrapes the live vLLM pod
- PromQL series in `infra/observability/promql/vllm-acceptance.yaml`
- Controlled load moves running/waiting or token/latency series
- Deleting `vllm-0` keeps the per-replica PVC cache

Record CPU, host RAM, GPU memory, disk, and Prometheus resource usage.

## Out of scope (STOP)

- Second replica / `kubectl scale --replicas=2`
- KEDA or any scaler
- Public ports, Ingress, NodePort, LoadBalancer
- Scale-to-zero
- `Qwen/Qwen3.5-9B` / `vast-k3s-replica-9b`
- Merging `phase-4`
- Destroying the VM from this runbook
