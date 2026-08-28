# Vast.ai rental checklist (Phase 3 VM)

Do **not** create or modify a Vast instance from this repository. Use this
page in the Vast console before you spend money. Provider stays configurable;
Vast is the first candidate. Phase 3 1.5B AWQ on k3s was accepted on one VM;
see [k3s-replica-1.5b-status.md](k3s-replica-1.5b-status.md). Do not rent a
replacement from here unless a later gate is approved.

Phase 2 Jupyter/container rentals are the wrong product. k3s needs a
**VM-capable** host with systemd, root, and nested containers.

## Exact Vast.ai filters

### Template (required)

1. Open [Vast templates](https://cloud.vast.ai/) → search **Ubuntu 22.04 VM**
   (or Ubuntu 24.04 VM if listed).
2. The image must stay in `docker.io/vastai/kvm` (for example
   `docker.io/vastai/kvm:ubuntu_terminal`). Do not switch it to a Jupyter,
   pytorch, or `vllm` Docker template.
3. In the template **Extra Filters** field, keep or add:

```text
vms_enabled=true
```

Official docs: https://docs.vast.ai/guides/instances/virtual-machines

That filter hides machines that cannot boot a KVM VM. SSH is the only launch
mode. Add your SSH public key on the Vast **Account** page **before** renting;
keys cannot be edited on a running VM.

### Search / offer filters

Use these in the Search UI (Create instance) **after** the VM template is
selected:

| Control | Set to |
|---|---|
| GPU | **RTX 3090** or **RTX 4090** (24 GiB). Do not pick 12 GiB cards for this gate. |
| GPU count | **1X** |
| Disk | **≥ 80 GB**, prefer **100 GB** |
| Ubuntu version | **22.04** (or 24.04 if you chose that VM image) |
| Min CUDA | **12.4** or newer (vLLM 0.27.1 images need a current driver/CUDA userland) |
| Driver | **≥ 550** |
| Interruptible vs on-demand | **On-Demand** for the first k3s bring-up |
| Secure cloud | Optional. Cheapest credible is usually community/consumer 3090/4090. |
| Unverified machines | Off unless you accept host risk |
| Static IP | Not required (SSH tunnel, no public API) |
| Internet down | Prefer **≥ 200 Mbps** so the vLLM image and 1.5B weights are not painful |
| Reliability | Prefer **≥ 0.98** if the slider is available |

Do **not** max GPU count. Do **not** select 2X/4X. Do **not** attach a Vast
provider persistent volume for this gate. The k3s `local-path` PVC lives on
the VM disk: it survives pod restarts and is lost when the Vast VM is
destroyed. That is not provider-persistent storage.

### CLI-shaped search (optional, do not execute from this repo)

If you use the Vast CLI later, the equivalent offer query looks like:

```text
gpu_name in [RTX_3090,RTX_4090] num_gpus=1 gpu_ram>=24000 disk_space>=80 cuda_max_good>=12.4 inet_down>=200
```

The CLI still must launch through a **VM** template with `vms_enabled=true`.
A matching GPU on a Docker/Jupyter template is a failed rental.

## What you must verify on the offer card before paying

- [ ] Template is a Vast **VM** (kvm image), not Jupyter / PyTorch container.
- [ ] Extra filter `vms_enabled=true` is present.
- [ ] Exactly **one** GPU; name is 3090 or 4090; VRAM **24 GB**.
- [ ] Disk **80–100+ GB**.
- [ ] Ubuntu 22.04 or 24.04.
- [ ] CUDA ≥ 12.4 and driver ≥ 550 as advertised.
- [ ] SSH key already uploaded to Vast.
- [ ] You will log in as **root** (or have root).
- [ ] You will **not** expose port 8000/18000 on the public internet.
- [ ] Price is acceptable for several hours of k3s + image pull (boot is slower than Docker instances).

## What you must verify after SSH (still before k3s)

Capture facts; do not install yet unless approved:

- [ ] `systemctl --version` works.
- [ ] `nvidia-smi` shows one 24 GiB GPU and driver ≥ 550.
- [ ] `df -h` shows enough free space for k3s + vLLM image + 1.5B cache (tens of GiB).
- [ ] `free -h` shows ≥ 16 GiB RAM (32 GiB preferred).
- [ ] This is not a nested-unfriendly container (`systemctl` failures mean wrong product).

Then run on the authoring Mac with a JSON facts file:

```bash
uv run python -m inference_platform.preflight.k8s_host_cli \
  --profile vast-k3s-replica --facts artifacts/phase3/host-facts.json
```

If the selected model does not fit: **stop**. Do not switch to 9B or 1.5B
silently. The 9B profile is `vast-k3s-replica-9b` and is opt-in after VRAM
discovery.

## Live Phase 3 gate (after you select a VM)

Do not rent from this repository. When you rent, the intended gate is:

- Official Vast **Ubuntu 22.04 VM** template
- Extra filter `vms_enabled=true`
- SSH key already registered before rental
- One RTX 3090 or RTX 4090 with 24 GiB VRAM
- At least 80 GiB disk, preferably 100 GiB
- One warm **1.5B AWQ** vLLM replica, TP=1, no Ray
- Single-node k3s
- SSH and Kubernetes port-forwarding only (no public API)

k3s `local-path` keeps the model cache across pod restarts. Destroying the
Vast VM deletes it. That is not provider-persistent storage.

## Documented 1.5B disk exception (already-rented VM)

The **rental recommendation is unchanged**: ≥80 GiB disk, preferably 100 GiB.
Vast cannot resize an existing instance disk
([FAQ](https://docs.vast.ai/guides/reference/faq/instances)) and volumes cannot
attach to VM instances
([volumes](https://docs.vast.ai/guides/instances/storage/volumes)).

A recorded filesystem of **72.5 GiB total / 55 GiB free** is allowed **only**
for `vast-k3s-replica` (1.5B AWQ). Details:
[ADR 0006](../decisions/0006-phase3-1.5b-disk-exception.md).

- `vast-k3s-replica-9b` remains **NO-GO** on that filesystem. Do not attempt it.
- Before installation: require ≥40 GiB free.
- After deployment and acceptance: require ≥15 GiB free.
- If either free-space limit is violated: stop and report. Do not delete
  caches, images, logs, or user files to satisfy the gate.

## Out of scope for this rental

Prometheus, KEDA, KubeRay, multi-node Ray, public HTTPS, scale-to-zero.
