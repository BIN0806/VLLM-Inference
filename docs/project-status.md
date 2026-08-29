# Final project status

## Completion

The scoped distributed inference lab is **complete**. PR #4 was merged to
`main` at commit
`64643039b8e3ea8c417c980de3fe8e62426097ac` and the annotated tag
`phase4-vast-k3s-2xa4000-keda-http-pass` marks the final accepted state.
CI passed on the final changes and merge. The last Vast.ai VM was gracefully
stopped and deleted.

This is an inference-serving project. It does not train, fine-tune, or prepare
datasets.

## Problem and design

The project addresses four serving concerns:

1. Model weights and KV cache must fit within GPU memory without silent model
   substitution.
2. Concurrent requests need efficient memory use and continuous scheduling.
3. Models that require more than one GPU need a coordinated execution topology.
4. Request capacity must grow by adding complete serving replicas, with a
   durable activation signal if the service reaches zero replicas.

The implementation separates those concerns:

- **vLLM** supplies PagedAttention, continuous batching, an OpenAI-compatible
  API, streaming SSE, and Prometheus metrics.
- **Tensor parallelism** shards one model replica across GPUs for model fit.
- **Ray** supplies a distributed executor and placement group for the ranks of
  one replica. The proven Ray path is same-host only.
- **Kubernetes/k3s** schedules GPU pods, manages health and lifecycle, exposes
  stable Services, and supplies the scale subresource.
- **Prometheus** scrapes replica metrics and evaluates the Phase 4B queue-depth
  signal.
- **KEDA** scales complete replicas. The Prometheus scaler proved 1→2→1; the
  HTTP add-on proved interceptor-driven 0→1→0.
- **Docker Compose** provides the smallest repository-owned single-GPU
  deployment path.

## Final request paths

### Single-container validation

```text
authoring client
  -> SSH local forward
    -> remote 127.0.0.1:8000
      -> pinned vLLM Compose container
        -> one GPU
```

### Warm horizontal scaling

```text
in-cluster load generator
  -> svc/vllm ClusterIP
    -> Ready replica 0 -> GPU 0 -> PVC 0
    -> Ready replica 1 -> GPU 1 -> PVC 1

Prometheus <- ServiceMonitor <- /metrics on each replica
KEDA       <- sum(vllm:num_requests_waiting)
```

### Scale-to-zero

```text
client
  -> durable KEDA HTTP interceptor
    -> svc/vllm
      -> zero or more Ready vLLM replicas

interceptor concurrency -> external scaler -> KEDA/HPA -> StatefulSet 0→1
```

vLLM metrics disappear when no replica exists. A Prometheus scaler therefore
cannot wake a zero-replica service by itself. The interceptor remains available,
observes HTTP concurrency, asks KEDA to activate the StatefulSet, and holds the
request until a backend is Ready.

## Component boundaries

| Component | Owns | Does not own |
|---|---|---|
| vLLM | Model execution, KV cache, batching, API, engine metrics | Pod placement or replica scaling |
| TP/PP ranks | One distributed replica | Independent horizontal capacity |
| Ray | Rank placement/execution for one replica | Kubernetes service lifecycle |
| Kubernetes | Pods, GPUs, Services, probes, volumes, scale target | LLM batching or model memory |
| Prometheus | Scrape and query | Holding requests at zero replicas |
| KEDA | Desired replica count | Scaling one TP rank independently |
| HTTP interceptor | Durable request observation and cold-start hold | TLS/HA in this lab |

## Phase evidence

| Gate | Hardware and topology | What passed | Boundary |
|---|---|---|---|
| Phase 0 | macOS authoring only | Pins, profiles, preflight, unit tests, ADR contract | No CUDA claim |
| Phase 1 | 1× RTX 3090, Qwen3.5-9B | 10/10 concurrent SSE; 90/90 benchmark requests | Existing vLLM process; no Compose claim at that point |
| Phase 2A | 2× RTX 3060 12 GiB, TP=2, native `mp` | Both ranks loaded, 10/10 SSE, 20/20 benchmark | Same host only; no comparison with Phase 1 hardware |
| Phase 2B | Same Phase 2 host, TP=2, Ray | Ray placement group/workers, 10/10 SSE, controlled executor comparison | Same-host Ray, not multi-node |
| Phase 3 | 1× RTX 3090, k3s, 1.5B AWQ | GPU scheduling, probes, SSE, pod restart, PVC cache reuse | One node and one warm replica |
| Phase 4A | 2× RTX A4000, one 1.5B AWQ replica | StatefulSet, per-ordinal PVC, ServiceMonitor, PromQL and live metrics | No scaler in this gate |
| Phase 4B | Same Phase 4 host, one GPU per replica | Manual 1→2, KEDA 1→2→1, 55%/45% ClusterIP distribution, about 2× throughput | Prometheus waiting-queue scaler; min=1 |
| Phase 4C | Same Phase 4 host, KEDA HTTP Add-on 0.15.0 | Interceptor 0→1, held request completed, normal 1→0, metrics absent at zero | One interceptor, beta add-on, no public TLS/HA, no HTTP 0→2 |
| Compose closeout | Same Phase 4 host after k3s stop | Pinned Dockerfile/Compose, GPU 0 only, loopback, 10/10 SSE, graceful down | One 1.5B container, not a scaler |

## Measured results

### Phase 1: single RTX 3090, 9B

- 90/90 steady-state requests succeeded at effective concurrency 10.
- About 172 input tokens/s, 90 output tokens/s, and 1.42 requests/s.
- TTFT p50/p95 about 2.1/4.2 s.
- E2E p50/p95 about 4.0/6.0 s.

### Phase 2A: two RTX 3060 GPUs, 9B TP=2, native multiprocessing

- About 34.06 input tokens/s and 17.13 output tokens/s.
- About 0.282 requests/s.
- TTFT p50/p95 about 14.2/28.5 s.
- About 10.6 GiB used on each 12 GiB GPU.

### Phase 2B: same host and contract, Ray executor

- About 34.94 input tokens/s and 18.26 output tokens/s.
- About 0.289 requests/s.
- Output throughput was 6.6% higher and TTFT p95 5.5% lower than the single
  native-`mp` run.

This is a one-run executor comparison, not proof that Ray is inherently faster.
Phase 1 and Phase 2 used different GPUs and configurations and are not a valid
TP speedup comparison.

### Phase 4B: replica scaling

- The in-cluster client created a new connection per request through the
  ClusterIP Service.
- After replica 1 became Ready, 270 recorded successes split 148/122 across
  replicas 0/1, or 55%/45%.
- Matched loaded windows increased from about 1.03 to 2.03 successful requests/s.
- Generation throughput increased from about 391 to 778 tokens/s.
- Scale detection took about 11 s; the warm second replica became Ready about
  141 s after container start; automatic scale-down followed the stabilization
  policy.

### Phase 4C: scale-to-zero

- At zero replicas both GPUs were idle, the two PVCs stayed Bound, vLLM series
  disappeared, and interceptor/scaler metrics remained available.
- One non-retried request caused 0→1, was held through a 150 s model startup,
  and completed after about 152.4 s.
- The response was HTTP 200 with
  `X-KEDA-HTTP-Cold-Start: true`, valid SSE, non-empty output, and
  `[DONE]`.
- A later normal 1→0 took about 327 s. GPUs returned to idle and vLLM metrics
  disappeared again.

### Compose closeout

- Pinned Dockerfile and `docker/compose.yaml` ran one 1.5B AWQ container on
  GPU 0.
- `/health` returned 200, `/v1/models` returned the expected alias,
  `/metrics` contained vLLM series, and 10/10 concurrent SSE streams passed.
- The host published only `127.0.0.1:8000`; GPU 1 remained idle.
- `docker compose down` removed the container, listener, and GPU process.

## Important failures and fixes

| Failure | Cause | Safe correction | Lesson |
|---|---|---|---|
| Hugging Face Xet request failed | Provider network/Xet token path | Disable Xet for acquisition; later serve from the pinned offline snapshot | Separate model acquisition from serving acceptance |
| 9B startup OOM | Template used 32k context and eight sequences on 12 GiB GPUs | Use the approved text-only 8k/two-sequence contract; no model fallback | Context and concurrency reserve KV memory |
| TP all-reduce issue | Cross-NUMA GPUs without P2P | Disable custom all-reduce and record topology | Hardware topology belongs in benchmark evidence |
| vLLM crash-loop in Kubernetes | Service links injected `VLLM_PORT=tcp://…` | Set `enableServiceLinks: false` | Platform-generated environment variables can collide with application config |
| Incomplete device-plugin apply | Patch fragment was applied as a full manifest | Reapply pinned manifest, then JSON-patch RuntimeClass | A kustomize patch is not a standalone resource |
| Port-forward used only one backend | Long-lived forwarding path was sticky | Use an in-cluster ClusterIP client with new TCP connections | Endpoint count alone is not load-distribution proof |
| Sparse TTFT/E2E p95 looked inverted | Short-window histogram samples and coarse buckets | Compare shared windows, counts, and sums; label as observability validation | Histogram quantiles require adequate samples |
| Compose could not select a GPU driver | Docker named an NVIDIA runtime but GPU/CDI wiring was incomplete | Configure NVIDIA Container Toolkit for Docker and enable CDI; do not rewrite k3s containerd | Docker and k3s use separate runtime configuration |
| Public Bearer test lacked TLS | Provider proxy endpoint was plaintext HTTP | Treat token as exposed, destroy rental, and add client transport guard | Authentication does not provide confidentiality |

## Memory and storage reasoning

A practical GPU budget is:

```text
GPU memory ≈ model weights + KV cache + runtime/workspace + safety headroom
```

AWQ reduces weight storage but does not automatically quantize the KV cache.
`max_model_len`, `max_num_seqs`, data type, and active request lengths
affect KV reservation. The implementation fails closed instead of silently
changing the model or TP degree.

Phase 4 used a StatefulSet because stable ordinals pair naturally with one
`local-path` RWO PVC per replica. This avoids concurrent writes to one Hugging
Face cache. The PVCs survive pod replacement and scale-in on the same VM, but
they are node-local and were deleted when the rental was destroyed.

## Security and lifecycle

- Live hosts, ports, tokens, instance IDs, fingerprints, kubeconfigs, and raw
  artifacts are excluded from the tracked tree.
- SSH host-key checking stayed enabled. Candidate fingerprints were verified
  before enrollment in the project-local, gitignored `.ssh/known_hosts`.
- vLLM and the HTTP interceptor were reached through SSH-tunneled loopback.
  No public inference, metrics, NodePort, LoadBalancer, or TLS endpoint was
  claimed.
- The client refuses to send credentials to non-loopback plaintext HTTP unless
  a prominent lab-only override is enabled.
- `trust_remote_code` stayed false.
- Teardown closed exact port-forward processes, stopped k3s gracefully, ran the
  final Compose validation, brought Compose down, confirmed idle GPUs and no
  listener, deleted the Vast VM, and confirmed later SSH failure.

## Reproducibility

- Immutable model revisions, image digest, chart versions, k3s release, and
  NVIDIA components are recorded in `configs/pins.yaml`.
- Configuration is layered by provider, compute topology, model, serving
  limits, workload, and environment.
- Offline acceptance covers lint, unit tests, profile/render guards, and Helm
  rendering. GPU gates are intentionally separate and require explicit flags.
- Raw run artifacts remain gitignored; sanitized evidence is tracked under
  `docs/runbooks/`.

Start with:

1. [Architecture](architecture.md)
2. [Feature pathway](feature-pathway.md)
3. [Personal use](personal-use.md)
4. [Benchmark contract](benchmark-contract.md)
5. [Operations](operations.md)
6. [ADRs](decisions/README.md)
7. The phase status reports under [runbooks](runbooks/)

## Final capabilities and goals

### Completed

- Pinned, serving-only vLLM configurations.
- Concurrent OpenAI-compatible SSE.
- Qwen3.5-9B TP=2 across two GPUs.
- Native multiprocessing and same-host Ray execution of the same TP contract.
- Single-node Kubernetes GPU scheduling, probes, Services, and restart recovery.
- Per-replica model caches that survive pod replacement on the same VM.
- Prometheus discovery and queries for vLLM metrics.
- KEDA Prometheus-driven 1→2→1 of complete replicas.
- ClusterIP load distribution and about 2× aggregate throughput at two Ready
  replicas.
- KEDA HTTP interceptor-driven lab 0→1→0 with one held request.
- Repository Docker Compose on one GPU over loopback.
- Graceful infrastructure teardown and rental deletion.

Training and fine-tuning remain intentionally outside this serving-only
project.

### Goals

- Extend Ray/KubeRay across multiple physical GPU nodes.
- Deploy the platform on managed EKS/GKE or multi-node Kubernetes.
- Add production HTTPS, public authentication, and interceptor HA.
- Exercise interceptor-driven 0→2.
- Autoscale independent 9B replicas on suitable GPUs.
- Define a frozen workload and evaluate the hardware required for 5,000 output
  tokens/s.

These are optional expansions beyond the completed lab.
