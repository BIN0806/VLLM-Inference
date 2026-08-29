# Architecture

This platform serves pretrained language models. It does not train or
fine-tune them. The completed implementation validates three related
topologies: a single GPU container, one model replica sharded across GPUs, and
multiple independent Kubernetes replicas.

## Design principles

1. **Fit and capacity are different problems.** Tensor parallelism helps one
   model fit or execute across GPUs. Independent replicas add request capacity.
2. **A replica is the scaling unit.** TP/PP/Ray ranks are inseparable parts of
   one replica. Kubernetes and KEDA scale complete replicas.
3. **Hardware is discovered.** GPU count, VRAM, topology, driver, disk, and RAM
   are rental-specific inputs, never project-wide constants.
4. **Fallback is fail-closed.** A model, TP, or hardware fallback requires an
   explicit flag and cannot pass the original gate.
5. **Zero replicas needs a durable signal.** vLLM metrics vanish at zero, so an
   interceptor must observe traffic and wake the service.
6. **Evidence is phase-scoped.** Results from different GPUs or workloads are
   not treated as topology speedups.

## Logical components

| Layer | Component | Responsibility |
|---|---|---|
| Client | Raw HTTPX SSE client and load generators | Validate OpenAI-compatible streaming, timing, concurrency, and terminal events |
| Engine | vLLM 0.27.1 | Model execution, PagedAttention, continuous batching, KV cache, API, metrics |
| Distributed execution | Native `mp` or Ray | Place and coordinate TP ranks for one replica |
| Container | Pinned Dockerfile/Compose | Smallest reproducible single-GPU serving path |
| Orchestrator | k3s/Kubernetes | GPU scheduling, lifecycle, probes, Services, PVCs, scale target |
| GPU integration | NVIDIA Container Toolkit, RuntimeClass, device plugin | Make GPUs allocatable and enforce one GPU request per replica |
| Observability | Prometheus + ServiceMonitor | Scrape and query per-replica vLLM metrics |
| Warm autoscaling | KEDA Prometheus scaler | Add/remove complete replicas from total waiting queue depth |
| Zero activation | KEDA HTTP Add-on interceptor | Stay available at zero, observe concurrency, hold the request, activate 0→1 |

## Topologies

### One complete replica on one GPU

```text
client -> vLLM API -> model replica -> GPU
```

Used for the Phase 1 9B validation, Phase 3/4 1.5B AWQ replicas, and the final
Compose gate. The model, context, concurrency, and GPU memory utilization must
fit one GPU.

### One complete replica sharded across two GPUs

```text
client -> vLLM API -> rank 0 on GPU 0
                   -> rank 1 on GPU 1
```

Phase 2A used native multiprocessing; Phase 2B used a same-host Ray placement
group. Both were TP=2 for one Qwen3.5-9B replica. They do not provide two
independent request-serving replicas.

### Two independent one-GPU replicas

```text
                         +-> vLLM-0 -> GPU 0 -> PVC 0
client -> ClusterIP svc -+
                         +-> vLLM-1 -> GPU 1 -> PVC 1
```

Phase 4 used one TP=1 replica per GPU. This is the topology that approximately
doubled aggregate throughput after the second pod became Ready.

## Kubernetes request path

```text
SSH-tunneled client
  -> KEDA HTTP interceptor ClusterIP
    -> svc/vllm ClusterIP
      -> Ready StatefulSet endpoints
        -> one GPU and one ordinal PVC per pod
```

- The StatefulSet gives each replica a stable ordinal and its own RWO
  `local-path` cache PVC.
- Each pod requests `nvidia.com/gpu: 1` and uses
  `runtimeClassName: nvidia`.
- `enableServiceLinks: false` prevents Kubernetes from injecting an invalid
  `VLLM_PORT=tcp://…` value.
- The startup probe tolerates model load; readiness removes unready replicas
  from the Service; liveness detects a stuck server after startup.
- The Service is ClusterIP. The lab did not publish inference publicly.

## Observability path

```text
vLLM /metrics
  -> per-replica metrics Service
    -> ServiceMonitor
      -> Prometheus
        -> PromQL / acceptance checks / KEDA trigger
```

Recorded families include running and waiting request gauges, KV-cache use,
prompt and generation token counters, request outcomes, TTFT histograms, and
end-to-end latency histograms.

Histogram quantiles are meaningful only with aligned windows and adequate
samples. The project records counts and sums and treats short-window p95 values
as observability validation rather than a production latency SLO.

## Autoscaling paths

### Warm 1→2→1

Phase 4B used:

```text
sum(vllm:num_requests_waiting)
  -> KEDA Prometheus trigger (metricType: Value, threshold: 1)
    -> HPA
      -> StatefulSet replicas 1..2
```

Waiting work is a better overflow signal than running work because
`max_num_seqs` caps admitted sequences. `metricType: Value` is required
because the query already returns one cluster-wide total.

### Zero 0→1→0

Phase 4C used:

```text
HTTP request
  -> durable interceptor concurrency
    -> external-push scaler
      -> KEDA/HPA
        -> StatefulSet 0..2
```

The accepted gate exercised 0→1 and a later normal 1→0. It did not exercise
interceptor-driven 0→2. The add-on was beta and used one interceptor replica,
so this is not a production availability or HA claim.

Only one ScaledObject/HPA may control `StatefulSet/vllm` at a time. Phase 4C
replaced the Phase 4B Prometheus ScaledObject instead of running competing
controllers.

## Storage

Each StatefulSet ordinal owns one 10 GiB `local-path` RWO PVC. This avoids
concurrent writes to one Hugging Face cache and lets a scaled-in ordinal reuse
its cache when it returns.

`local-path` is node-local:

- survives pod deletion and recreation on the same VM;
- remains Bound during StatefulSet scale-in;
- does not survive node or Vast VM destruction;
- is not provider-persistent or multi-node shared storage.

A production multi-node version would require explicit object-backed model
distribution, image-baked weights, or a suitable RWX/provider-persistent
strategy.

## Configuration layers

Profiles compose independent provider, compute, model, serving, workload, and
environment layers:

```text
provider/connection + hardware + model + serving + workload + environment
                              -> composed profile
```

Changing rentals should change connection and discovered hardware values, not
model or benchmark semantics. Model and image revisions remain immutable.

## Runtime separation

The authoring Mac runs docs, lint, unit tests, rendering, preflight, clients,
and SSH forwarding. It is not an NVIDIA host and cannot pass GPU acceptance.

The k3s path uses embedded containerd. The Compose path uses Docker. NVIDIA
runtime configuration for one must not be written into the other. The final
Compose gate needed Docker-specific NVIDIA Toolkit/CDI configuration after
k3s was stopped.

## Security boundary

- Live access stayed on loopback through SSH.
- Inference, metrics, and interceptor Services stayed ClusterIP.
- Host-key checking remained enabled.
- Secrets and rental identifiers stayed in ignored local files.
- `trust_remote_code` remained false.
- No public TLS, Ingress, NodePort, LoadBalancer, or interceptor HA was
  installed.

## Lifecycle and final state

The final lab progressed from one warm replica, through Prometheus and KEDA,
to scale-to-zero. Closeout then:

1. closed port-forwards;
2. stopped k3s gracefully;
3. ran the repository Compose acceptance on GPU 0;
4. brought Compose down;
5. confirmed no listener or GPU compute process remained;
6. deleted the Vast VM and confirmed later SSH failure.

The VM-local PVCs and caches were intentionally lost with the rental. Git and
the tracked, sanitized runbooks are the source of truth.

See [Final project status](project-status.md) for the evidence and claim matrix.
