# k3s + NVIDIA on a GPU VM (documentation only)

**Do not run these commands from this repository until Phase 3 infrastructure is
explicitly approved.** This page is a checklist for a future Linux GPU VM with
root and systemd. It is not an installer.

Phase 3 first gate: single-node k3s, one GPU, one warm vLLM replica, no Ray,
no Prometheus, no KEDA, no KubeRay.

## Assumptions

- The host is a **VM**, not a Vast Jupyter/Docker template. `systemctl` works.
- You are root (or can become root).
- Ubuntu 22.04 or 24.04, x86_64.
- NVIDIA driver already works (`nvidia-smi`).
- Kubernetes version will fall in the pin window `1.33–1.35` (`configs/pins.yaml`).
- NVIDIA device plugin **0.20.0**.
- vLLM image digest comes from `configs/pins.yaml`, not `latest`.

## 1. NVIDIA Container Toolkit

Follow NVIDIA's current install guide for your Ubuntu version:

https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html

After install, the NVIDIA runtime must be available to **k3s containerd**, not
only to Docker. Typical k3s integration copies or generates a containerd
config that includes the NVIDIA runtime and restarts k3s. Do not skip the
k3s-specific containerd path (`/var/lib/rancher/k3s/agent/etc/containerd/`).

Prove with a GPU-enabled container **after** k3s is up, not before you need it.

## 2. k3s

Pick a k3s release whose embedded Kubernetes version is in **1.33–1.35**.
List releases at https://github.com/k3s-io/k3s/releases rather than installing
an unpinned `latest`.

Example shape only (do not run until approved):

```bash
# Replace the version after checking the k3s release list.
# curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=vX.Y.Z+k3s1 sh -
```

Disable k3s Traefik only if you do not want a public Ingress. The first
acceptance gate uses **SSH + kubectl port-forward** to loopback, not a public
LoadBalancer.

kubeconfig on the node is normally `/etc/rancher/k3s/k3s.yaml`. Do not commit
it. Copying it to the authoring Mac is optional; port-forward can run on the
VM and be tunneled with SSH.

## Storage (k3s local-path)

The model cache PVC uses k3s `local-path`. That volume **persists across pod
restarts** on the same VM. It **does not survive destruction of the Vast VM**.
It is node-local disk, not provider-persistent storage. Destroying the rental
deletes the weights. Do not describe this PVC as a Vast persistent volume.

## 3. NVIDIA Kubernetes device plugin 0.20.0

This is **cluster infrastructure**, not an application sidecar. Pin:

https://github.com/NVIDIA/k8s-device-plugin/releases/tag/v0.20.0

Example shape only (do not apply until approved):

```bash
# kubectl apply -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.20.0/deployments/static/nvidia-device-plugin.yml
```

Confirm `kubectl describe node` shows `nvidia.com/gpu: 1` (or more). The vLLM
Deployment requests `nvidia.com/gpu: 1`.

## 4. Application manifests

On the authoring workstation (offline):

```bash
make k8s-render K8S_PROFILE=vast-k3s-replica
```

That writes `infra/kubernetes/base`. Create the Secret on the cluster from
`secret.yaml.example` with `kubectl create secret` / `--from-literal`. Never
commit `HF_TOKEN` or `VLLM_API_KEY`.

Do not `kubectl apply` until a later approval. Do not install Prometheus,
KEDA, or KubeRay in this gate.

## 5. Access

On the GPU VM, after the Deployment is Ready:

```bash
# kubectl -n inference port-forward svc/vllm 8000:8000 --address 127.0.0.1
```

From the authoring Mac, SSH-forward that loopback port (existing
`make tunnel` once `VLLM_REMOTE_PORT` matches). Do not publish NodePort or a
public HTTP URL for the first gate.

## Stop

If `nvidia.com/gpu` is missing, if systemd is absent, or if the selected model
does not fit discovered VRAM: **fail closed**. Do not change the model or set
TP=2 to compensate.
