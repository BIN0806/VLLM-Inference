# k3s + NVIDIA on a GPU VM

Phase 3 first gate: single-node k3s, one GPU, one warm **1.5B AWQ** vLLM replica,
TP=1, PP=1, no Ray, no Prometheus, no KEDA, no KubeRay. Access is SSH plus
`kubectl port-forward` to loopback. Do not publish NodePort or a public HTTP URL.

This page is a pinned checklist, not a `make` installer. Do not install 9B.

## Pins

| Component | Pin | Source |
|---|---|---|
| k3s | `v1.34.10+k3s1` (Kubernetes v1.34.10) | `https://get.k3s.io` / [GitHub release](https://github.com/k3s-io/k3s/releases/tag/v1.34.10+k3s1) |
| k3s linux/amd64 | sha256 `e63a3511b2603fd1436a1ea8d228348a3b47334b45024801d41a8c0e2d22e8c4` | release `sha256sum-amd64.txt` |
| NVIDIA device plugin | 0.20.0 | [tag](https://github.com/NVIDIA/k8s-device-plugin/releases/tag/v0.20.0) |
| vLLM image | digest in `configs/pins.yaml` | never `latest` |

Never install an unpinned `latest` k3s channel.

## Disk exception (1.5B only)

A documented exception for one already-rented 72.5 GiB VM applies only to
`vast-k3s-replica`. The rental recommendation remains ≥80 GiB, preferably 100 GiB.
Require ≥40 GiB free before install and ≥15 GiB free after acceptance.
`vast-k3s-replica-9b` stays NO-GO. Do not delete files to satisfy those floors.
See [ADR 0006](../decisions/0006-phase3-1.5b-disk-exception.md).

## Assumptions

- The host is a **VM** with systemd, root, Ubuntu 22.04/24.04 x86_64.
- NVIDIA driver already works (`nvidia-smi`).
- NVIDIA Container Toolkit is already present for Docker; k3s uses **embedded
  containerd**, not Docker.

## 1. NVIDIA runtime for k3s containerd

Do **not** run `nvidia-ctk runtime configure` against
`/var/lib/rancher/k3s/agent/etc/containerd/config.toml.tmpl`. That overwrites
the k3s template and can break CNI.

k3s natively registers NVIDIA when `nvidia-container-runtime` is on PATH.
Write `/etc/rancher/k3s/config.yaml` **before** install (or restart k3s after):

```yaml
write-kubeconfig-mode: "600"
disable:
  - traefik
  - servicelb
nvidia-container-runtime-endpoint: /usr/bin/nvidia-container-runtime
```

Confirm after k3s is up: `grep nvidia /var/lib/rancher/k3s/agent/etc/containerd/config.toml`
and `kubectl get runtimeclass nvidia`. GPU pods must set `runtimeClassName: nvidia`
(see `infra/kubernetes/overlays/vast-k3s/runtime-class-patch.yaml`).

## 2. k3s (embedded containerd)

```bash
# Pin from configs/pins.yaml. Do not omit INSTALL_K3S_VERSION.
# curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=v1.34.10+k3s1 sh -
```

The install script reads `/etc/rancher/k3s/config.yaml`. Disable Traefik and
ServiceLB so this gate has no public Ingress or LoadBalancer. kubeconfig is
`/etc/rancher/k3s/k3s.yaml`. Do not commit it.

## Storage (k3s local-path)

The model cache PVC uses k3s `local-path`. That volume **persists across pod
restarts** on the same VM. It **does not survive destruction of the Vast VM**.
It is node-local disk, not provider-persistent storage. Destroying the rental
deletes the weights. Do not describe this PVC as a Vast persistent volume.

## 3. NVIDIA Kubernetes device plugin 0.20.0

Cluster infrastructure, not an application sidecar. Apply the pinned manifest,
then the k3s kubelet path + RuntimeClass patch:

```bash
# kubectl apply -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.20.0/deployments/static/nvidia-device-plugin.yml
# kubectl apply -f infra/kubernetes/overlays/vast-k3s/nvidia-device-plugin-k3s-patch.yaml
```

k3s kubelet device-plugin sockets live at
`/var/lib/rancher/k3s/agent/kubelet/device-plugins`, not `/var/lib/kubelet/...`.

Confirm `kubectl describe node` shows `nvidia.com/gpu: 1`.

## 4. Application manifests

```bash
make k8s-render K8S_PROFILE=vast-k3s-replica
kubectl apply -k infra/kubernetes/overlays/vast-k3s
```

Apply only the 1.5B profile. Do not apply `vast-k3s-replica-9b`. Create the
Secret from `secret.yaml.example` if needed. Never commit `HF_TOKEN` or
`VLLM_API_KEY`. Do not install Prometheus, KEDA, or KubeRay.

## 5. Access

```bash
kubectl -n inference port-forward svc/vllm 8000:8000 --address 127.0.0.1
```

From the authoring Mac, SSH-forward that loopback port (`make tunnel` with
`VLLM_REMOTE_PORT=8000`). The Service stays ClusterIP.

## Stop

If `nvidia.com/gpu` is missing, if systemd is absent, if free disk violates the
exception floors, or if the selected model does not fit: **fail closed**. Do not
change the model or set TP=2 to compensate. Do not delete caches to recover
space.
