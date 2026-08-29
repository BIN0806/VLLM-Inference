# Architecture

This platform serves pretrained models with vLLM. It does not train or fine-tune.

## Replica model

```text
Clients
  -> optional gateway / KEDA HTTP interceptor (later)
    -> stable router
      -> complete inference replica A (vLLM, 1..N GPUs)
      -> complete inference replica B
      -> ...
```

- **Tensor parallelism (TP)** shards one replica across GPUs. It is a model-fit choice.
- **Pipeline parallelism (PP)** places layer groups on different workers. Prefer TP within a node and PP across nodes when a later multi-node profile exists.
- **Independent replicas** put one complete model copy on each GPU to raise request throughput. This is not TP.
- **Kubernetes replicas** are complete serving units. KEDA must add or remove whole replicas, never individual TP/PP ranks.
- **Ray multi-node** is one distributed topology spanning independently scheduled hosts. A single multi-GPU machine using Ray is `ray-single-host`, not multi-node.

## Environments

| Environment | Role | GPU gate |
|---|---|---|
| macOS authoring workstation | Docs, lint, unit tests, HTTP client | Not applicable |
| Provider overlay + compute profile (currently `vast` + `single-gpu`) | Real CUDA/vLLM validation over SSH | Required, remote |
| `k8s-replica` | First Kubernetes MVP, minReplicas=1 | Phase 3 1.5B AWQ on k3s accepted |
| `k8s-replicas` | Two-replica-capable StatefulSet, one GPU per pod | Phase 4A: one replica + Prometheus scrape; KEDA not installed |
| `k8s-replica-zero` | Later scale-to-zero | Requires durable interceptor |
| `ray-multinode` | True multi-node | `NOT RUN — HARDWARE UNAVAILABLE` |

The authoring Mac is not `local-1gpu`. The GPU is remote.

## Scale-to-zero

vLLM-only Prometheus series vanish when no vLLM pod exists, so they cannot wake a zero-replica service. A persistent interceptor or gateway must remain available. That profile is later; the first Kubernetes MVP keeps one warm replica.

## Configuration

Independent layers: provider/connection, hardware topology, model, serving, workload, deployment environment. Composed profiles live in `configs/profiles/`. Connection details are environment variables, never committed IPs or keys.

## Fallback

Default is fail-fast. TP, model, and offline-test fallbacks require explicit flags, prominent console output, and a report field. A fallback result cannot pass the originally requested hardware gate.

## Remote host

Vast rentals are ephemeral and have no persistent volume. Git on the authoring workstation is the source of truth. Model caches and logs on the rental are disposable. SSH uses the user agent, never reads private-key contents, and never disables host-key checking. First-contact host keys are stored in the project `.ssh/known_hosts` file after fingerprint verification.
