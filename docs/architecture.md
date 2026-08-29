# Architecture

This platform serves pretrained models with vLLM. It does not train or fine-tune.

## Replica model

```text
Clients
  -> KEDA HTTP interceptor ClusterIP (lab; SSH + port-forward only)
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
| `k8s-replicas` | Two-replica-capable StatefulSet, one GPU per pod | Phase 4C: HTTP interceptor lab scale-to-zero; Phase 4B 1→2→1 retained as historical scaler |
| `k8s-replica-zero` | Documented zero-replica profile | Validated via the existing StatefulSet + HTTP ScaledObject; renderer still refuses replica_count 0 |
| Docker Compose (`docker/compose.yaml`) | One pinned vLLM container, loopback publish | Closeout GO: 1.5B AWQ on GPU 0 after k3s stop; not 9B |
| `ray-multinode` | True multi-node | `NOT RUN — HARDWARE UNAVAILABLE` |

The authoring Mac is not `local-1gpu`. The GPU is remote.

## Scale-to-zero

vLLM-only Prometheus series vanish when no vLLM pod exists, so they cannot wake
a zero-replica service. Phase 4C keeps a durable KEDA HTTP Add-on 0.15.0
interceptor (**one** replica, ClusterIP) in front of `svc/vllm`. Clients reach
it only through SSH plus `kubectl port-forward`. That is a **single-node lab**
validation; the add-on is **beta** and production TLS/HA are not proven.

Two scaler proofs stay distinct:

- Phase 4B: Prometheus-driven **1→2** on `sum(vllm:num_requests_waiting)`.
- Phase 4C: interceptor-driven **0→1** on HTTP concurrency.

HTTP **0→2** was not tested.

## Configuration

Independent layers: provider/connection, hardware topology, model, serving, workload, deployment environment. Composed profiles live in `configs/profiles/`. Connection details are environment variables, never committed IPs or keys.

## Fallback

Default is fail-fast. TP, model, and offline-test fallbacks require explicit flags, prominent console output, and a report field. A fallback result cannot pass the originally requested hardware gate.

## Remote host

Vast rentals are ephemeral and have no persistent volume. Git on the authoring workstation is the source of truth. Model caches and logs on the rental are disposable. SSH uses the user agent, never reads private-key contents, and never disables host-key checking. First-contact host keys are stored in the project `.ssh/known_hosts` file after fingerprint verification.

The repository Compose path is a single-container lab serve: pinned
`docker/Dockerfile` + `docker/compose.yaml`, `HOST_BIND=127.0.0.1`, SSH
tunnel from the authoring Mac. It is not a replica scaler and is not a
public bind. Live closeout:
[compose-1.5b-status.md](runbooks/compose-1.5b-status.md).
