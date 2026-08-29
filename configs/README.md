# Configuration model

The repository separates values that change for different reasons:

1. **Provider and connection** — gitignored environment values.
2. **Compute topology** — GPU/replica/TP/Ray/Kubernetes shape.
3. **Model** — immutable model id, revision, quantization, and fit estimate.
4. **Serving** — context, sequences, memory utilization, executor, API flags.
5. **Workload** — prompts, output length, concurrency, timeout, measurement.
6. **Environment** — authoring, remote GPU host, Compose, or Kubernetes.

A composed profile names these layers. Changing a Vast rental should normally
change only connection values and discovered hardware—not model or workload
semantics.

## Compute profiles

| Profile | Purpose | Live status |
|---|---|---|
| `single-gpu` | One complete replica on one GPU | Proven |
| `multi-gpu-tp` | One replica sharded with tensor parallelism | Proven at TP=2 |
| `multi-gpu-replicas` | Independent one-GPU replicas | Proven through Kubernetes |
| `ray-single-host` | Ray executor for one multi-GPU replica | Proven |
| `ray-multinode` | One distributed replica across physical nodes | Future goal |
| `k8s-replica` | One warm Kubernetes replica | Proven |
| `k8s-replicas` | One-to-two complete replicas | Proven |
| `k8s-replica-zero` | Durable-front-door zero-replica topology | 0→1 proven through the Phase 4 StatefulSet/HTTP ScaledObject; renderer still refuses a literal zero-replica base |

## Composed profiles

| Profile | Model/topology | Status |
|---|---|---|
| `authoring` | No GPU; docs/tests/preflight | Proven as non-CUDA |
| `vast-single-gpu` | Qwen3.5-9B, one GPU | Phase 1 proven |
| `vast-two-gpu` | Qwen3.5-9B, TP=2 | Phase 2 native `mp` and same-host Ray proven |
| `vast-k3s-replica` | 1.5B AWQ, one GPU, k3s | Phase 3 proven; also final Compose input profile |
| `vast-k3s-replica-9b` | 9B, one-GPU k3s opt-in | Future goal; requires a new fit gate |
| `vast-k3s-replicas` | 1.5B AWQ StatefulSet, one GPU/pod | Phase 4 Prometheus, KEDA 1→2, and HTTP 0→1 proven |

## Invariants

- Do not commit provider hosts, ports, instance IDs, API keys, SSH keys, or
  model tokens.
- Do not silently change the selected model or tensor-parallel size.
- A fallback cannot pass the original gate.
- Hardware discovery must validate count, VRAM, topology, driver, disk, and RAM.
- Pinned component versions live in `configs/pins.yaml`; never use
  unreviewed `latest` tags.
- The 5,000-output-token/s idea is aspirational and not an acceptance value.

See [Architecture](../docs/architecture.md) and
[Final project status](../docs/project-status.md).
