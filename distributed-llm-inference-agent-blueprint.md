# Distributed LLM Inference Platform — Implementation Blueprint

> Copy this document into the coding agent's workspace as the authoritative project brief. The agent must implement the project one phase at a time, verify every phase with real tests, and wait for approval before beginning the next phase.

## 1. System role

Act as a Senior MLOps and Distributed Systems Engineer. Architect, implement, test, benchmark, and document an end-to-end distributed LLM inference platform using:

- vLLM for OpenAI-compatible model serving, PagedAttention, KV-cache management, and continuous batching.
- Docker and Docker Compose for local development.
- Kubernetes for workload orchestration.
- Ray for genuine multi-node distributed execution.
- KubeRay for Kubernetes-native Ray clusters.
- Prometheus for metrics collection.
- KEDA for event-driven horizontal scaling.
- The KEDA HTTP Add-on, or an explicitly approved equivalent, for HTTP scale-to-zero.

The system serves pretrained models only. Do not generate training, pretraining, fine-tuning, LoRA training, dataset preparation, gradient computation, optimizer, or checkpoint-training code.

## 2. Mandatory execution protocol

1. Read this entire document before changing files.
2. Do not build the entire system in one pass.
3. Begin with Phase 0 only after receiving an explicit instruction to begin.
4. At the beginning of each phase:
   - State the phase objective.
   - List the files that will be created or changed.
   - State which deployment profile and hardware profile are being exercised.
   - Identify any assumptions that affect the phase gate.
5. At the end of each phase:
   - Run all tests required by the phase gate.
   - Report the exact commands run and their exit status.
   - Summarize measured results; do not report a test as passing without evidence.
   - List every created or changed file.
   - Document unresolved risks or deviations.
   - Stop and wait for approval before starting the next phase.
6. A mocked GPU, syntax-only manifest check, or simulated Ray resource must never be reported as proof that real GPU or multi-node inference works.
7. Preserve unrelated user changes. Do not destructively reset the repository.
8. Never commit credentials, Hugging Face tokens, API keys, kubeconfigs, cloud credentials, private registry credentials, or generated secrets.
9. Never use floating production dependencies such as `latest` in committed runtime configuration. Phase 0 must resolve and record exact versions or immutable image digests.
10. Prefer official project images, charts, APIs, and documentation over third-party wrappers.

## 3. Project mission

Build a reproducible, observable, and horizontally scalable LLM serving platform that:

- Exposes an OpenAI-compatible streaming API.
- Serves a small quantized model on constrained NVIDIA hardware for development.
- Supports one or more GPUs inside a complete inference replica.
- Validates Ray as the distributed backend.
- Supports true multi-node inference through KubeRay when suitable hardware exists.
- Scales complete inference replicas in response to real demand.
- Avoids OOM failure during the documented workload envelope.
- Measures throughput, Time to First Token (TTFT), inter-token latency, queue time, and error rate.
- Reuses pinned model weights after restart instead of repeatedly downloading them.
- Provides explicit cold-start behavior if scale-to-zero is enabled.
- Can be operated and diagnosed from its documentation and metrics.

## 4. Non-goals and hard boundaries

The following are out of scope unless a later written requirement explicitly adds them:

- Model training or fine-tuning of any kind.
- Dataset pipelines or feature engineering.
- Automatic selection among unrelated models.
- Multi-tenant model hosting in the first implementation.
- Dynamic LoRA loading.
- Speculative decoding, disaggregated prefill/decode, or external KV-cache systems in the MVP.
- Treating Apple unified memory, AMD ROCm, or CPU inference as interchangeable with the NVIDIA CUDA acceptance path.
- Claiming production readiness from a local Kind or Minikube demonstration alone.
- Scaling individual tensor-parallel or pipeline-parallel ranks independently.

The primary MVP target is Linux with NVIDIA CUDA-capable GPUs. Other accelerators require separate profiles and acceptance tests.

## 5. Architecture model and terminology

```text
External clients
      |
      v
Ingress / Gateway / KEDA HTTP interceptor
      |
      v
Stable Kubernetes Service or request router
      |
      +--------------------+--------------------+
      |                    |                    |
      v                    v                    v
Inference replica A  Inference replica B  Inference replica C
  vLLM engine          vLLM engine          vLLM engine
  1..N GPUs            1..N GPUs            1..N GPUs
      |                    |                    |
      +--------------------+--------------------+
                           |
                  Versioned model storage

Prometheus scrapes gateway, vLLM, Kubernetes, and GPU metrics
      |
      v
KEDA scales complete inference replicas, never individual TP/PP ranks
```

### 5.1 Tensor parallelism

Tensor parallelism, or TP, shards operations for one model replica across multiple GPUs. It is primarily a model-fit and per-replica execution strategy. It may improve latency or throughput when compute savings outweigh communication overhead, but it may also reduce performance on small models or slow interconnects. TP is not horizontal request scaling.

### 5.2 Pipeline parallelism

Pipeline parallelism, or PP, places different layer groups on different workers. It is often more suitable than cross-node TP when inter-node networking is slower than an intra-node GPU interconnect. For multi-node vLLM, the preferred starting topology is generally TP within a node and PP across nodes, followed by measurement.

### 5.3 Horizontal replica scaling

Horizontal scaling adds independent, complete inference replicas. Each replica must contain all of the GPUs and workers required by its TP/PP topology. KEDA may scale a normal vLLM Deployment whose pods are self-contained replicas. It must not scale one rank or worker from an existing distributed replica.

### 5.4 Scale-to-zero

Metrics emitted only by vLLM disappear when no vLLM pod exists. A durable component must remain available to observe new traffic, hold or reject requests predictably, and trigger activation. The default design is the KEDA HTTP Add-on interceptor in front of the vLLM Service.

### 5.5 Ray's role

Use native vLLM multiprocessing for the normal same-host multi-GPU path. Use Ray to prove backend compatibility and for genuine multi-node execution. Do not add Ray to the single-GPU baseline merely to satisfy a technology checklist.

## 6. Supported deployment profiles

The repository must expose explicit profiles instead of trying to make one configuration cover incompatible topologies.

| Profile | Purpose | Topology | Horizontal scaler | Required gate |
|---|---|---|---|---|
| `local-1gpu` | Fast functional baseline | Docker, one vLLM process, TP=1 | None | Real NVIDIA GPU |
| `local-2gpu-mp` | Same-host sharding | Docker, one replica, TP=2, multiprocessing | None | Two real GPUs |
| `local-2gpu-ray` | Ray backend validation | Docker/Ray, one replica, TP=2 | None | Two real GPUs plus Ray evidence |
| `k8s-replica` | Recommended MVP | One Kubernetes pod is one complete replica; it requests all GPUs it needs | KEDA scales the Deployment | GPU-capable Kubernetes node(s) |
| `k8s-replica-zero` | HTTP scale-to-zero | Same as `k8s-replica`, behind KEDA HTTP interceptor | KEDA HTTP Add-on | Cold-start and streaming tests |
| `k8s-ray-multinode` | Advanced distributed model replica | RayService/RayCluster with head and workers, TP/PP topology | Not KEDA by default | At least two physical GPU nodes |

The first production candidate should be `k8s-replica`. The Ray multi-node profile is a separately validated capability. Combining KEDA horizontal scaling with complete multi-node Ray replicas requires a later controller design and is not achieved by scaling Ray worker counts blindly.

## 7. Baseline model policy

Use a small, public, instruction-tuned model for the initial functional path. The default candidate is:

```text
Qwen/Qwen2.5-1.5B-Instruct-AWQ
```

Requirements:

- Resolve and pin an immutable Hugging Face revision during Phase 0.
- Record the model license and source URL.
- Use a stable served-model alias so API clients do not depend on a filesystem path.
- Do not enable `trust_remote_code` unless it is proven necessary, reviewed, and documented in an architecture decision record.
- Do not assume that the 1.5B model is representative of TP performance. Phase 2 may select a second, larger pinned model to make multi-GPU behavior meaningful, but the Phase 1 model must remain available for fast regression testing.
- Quantization is for memory efficiency, not a guaranteed throughput improvement. Benchmark it.

## 8. Performance and SLO contract

The phrase “5,000 tokens per second” is not an acceptance criterion until all variables below are fixed.

### 8.1 Required workload definition

Document the following in `docs/benchmark-contract.md`:

- GPU model, count, VRAM, driver, and relevant interconnect.
- CPU model/count and host RAM.
- Operating system and container runtime.
- Model ID, exact revision, quantization, dtype, and served alias.
- vLLM image digest and engine arguments.
- Minimum, median, p95, and maximum input length in tokens.
- Requested output-token count or distribution.
- Concurrency levels and arrival pattern.
- Streaming behavior.
- Warm-up duration.
- Measurement duration.
- Success definition and timeout.
- Whether prefix caching is enabled and whether prompts share prefixes.

### 8.2 Required metrics

Measure at least:

- Input tokens/second.
- Output tokens/second.
- Requests/second.
- p50, p95, and p99 TTFT.
- p50 and p95 inter-token latency or time per output token.
- p50 and p95 end-to-end latency.
- p95 queue time.
- Request success and error rate.
- HTTP timeout count.
- OOM count and container/pod restart count.
- Peak GPU memory utilization.
- KV-cache utilization.
- Number of running and waiting requests.

### 8.3 Metric definitions

- Aggregate output tokens/sec = total successfully generated output tokens divided by the steady-state measurement window.
- Aggregate input tokens/sec = total successfully processed prompt tokens divided by the steady-state measurement window.
- TTFT = time from request dispatch to receipt of the first generated-content streaming chunk.
- End-to-end latency = time from request dispatch to the terminal stream event.
- Error rate = failed or invalid requests divided by all attempted requests.

Exclude warm-up requests from steady-state performance calculations, but report warm-up and model-load times separately. Save raw per-request measurements as machine-readable JSON or JSON Lines so percentile calculations can be reproduced.

## 9. Repository contract

Create and maintain the following structure. A file may be omitted only when the phase that owns it has not begun.

```text
.
├── README.md
├── Makefile
├── pyproject.toml
├── uv.lock                         # or another committed deterministic lock file
├── .env.example
├── .gitignore
├── docker/
│   ├── Dockerfile
│   ├── compose.yaml
│   └── README.md
├── config/
│   ├── model.env.example
│   └── profiles/
│       ├── local-1gpu.env
│       ├── local-2gpu-mp.env
│       └── local-2gpu-ray.env
├── scripts/
│   ├── preflight.py
│   ├── download_model.py
│   ├── wait_for_service.py
│   └── collect_diagnostics.py
├── tests/
│   ├── conftest.py
│   ├── test_preflight.py
│   ├── test_phase1.py
│   ├── benchmark_phase1.py
│   ├── test_phase2.py
│   ├── test_phase3.py
│   ├── load_phase4.py
│   └── watch_scaling.py
├── infra/
│   ├── kubernetes/
│   │   ├── base/
│   │   └── overlays/
│   │       ├── local/
│   │       ├── eks/
│   │       └── gke/
│   ├── ray/
│   └── observability/
├── docs/
│   ├── architecture.md
│   ├── benchmark-contract.md
│   ├── operations.md
│   ├── security.md
│   ├── troubleshooting.md
│   └── decisions/
├── artifacts/                      # ignored generated test and benchmark output
└── .github/workflows/              # or the repository's existing CI location
```

Do not copy generated model weights, Python virtual environments, benchmark artifacts, or credentials into version control.

## 10. Configuration contract

Centralize configuration and document every setting. At minimum support:

| Setting | Purpose |
|---|---|
| `VLLM_IMAGE` | Pinned image tag and preferably immutable digest |
| `MODEL_ID` | Upstream model repository identifier |
| `MODEL_REVISION` | Immutable model revision |
| `MODEL_PATH` | Local, container-visible versioned snapshot path |
| `SERVED_MODEL_NAME` | Stable API-facing model alias |
| `HOST_PORT` / `CONTAINER_PORT` | API binding, defaulting to 8000 where appropriate |
| `TENSOR_PARALLEL_SIZE` | GPUs used for TP inside one replica |
| `PIPELINE_PARALLEL_SIZE` | PP stages inside one distributed replica |
| `DISTRIBUTED_EXECUTOR_BACKEND` | `mp` or `ray`, selected by profile |
| `GPU_MEMORY_UTILIZATION` | Bounded vLLM GPU memory fraction |
| `MAX_MODEL_LEN` | Maximum context length used for capacity planning |
| `MAX_NUM_SEQS` | Maximum concurrent sequences admitted by the engine |
| `HF_HOME` | Persistent cache location |
| `HF_TOKEN` | Optional secret, never committed |
| `VLLM_API_KEY` | Optional API secret, never committed |
| `RAY_ADDRESS` | Ray cluster address for Ray profiles |

Rules:

- `.env.example` contains placeholders and safe defaults only.
- Secrets are supplied by the environment, a local untracked file, or Kubernetes Secrets/external secret management.
- Validate numeric ranges before startup.
- Record effective, non-secret configuration in diagnostic output.
- Avoid duplicating divergent defaults across Compose, Kubernetes, tests, and documentation.

## 11. Phase 0 — Environment, dependency, and benchmark contract

### Objective

Freeze the target environment and make every later claim reproducible.

### Deliverables

1. `scripts/preflight.py`
2. Unit tests for the preflight logic.
3. `docs/benchmark-contract.md`
4. Initial `docs/architecture.md`
5. Architecture decision records for:
   - Primary deployment profile.
   - Baseline model and immutable revision.
   - Dependency-version policy.
   - Autoscaling boundary.
6. Pinned project and test dependencies.
7. A generated, ignored preflight report under `artifacts/`.

### Preflight behavior

`scripts/preflight.py` must:

- Accept an explicit profile such as `--profile local-1gpu`.
- Produce readable terminal output and machine-readable JSON.
- Return zero only when all mandatory checks for that profile pass.
- Distinguish `PASS`, `WARN`, `SKIP`, and `FAIL`.
- Never expose secret values.
- Check:
  - Supported Linux architecture for the NVIDIA MVP.
  - Python version.
  - Docker engine and Compose availability.
  - NVIDIA driver visibility.
  - Physical GPU count, model, total VRAM, and free VRAM.
  - GPU accessibility from an NVIDIA CUDA container.
  - Host RAM and free disk capacity.
  - Availability of the configured API port.
  - Shared-memory capacity or the ability to configure it.
  - Required executables for the selected phase.
  - Kubernetes connectivity, Helm, and GPU resources only for Kubernetes profiles.
  - Ray connectivity only for Ray profiles.
- Clearly explain remediation for failures.

Do not require cloud or Kubernetes tools for the `local-1gpu` profile.

### Version resolution

Record exact compatible versions for:

- vLLM image.
- Python.
- OpenAI Python client or HTTP client.
- Ray.
- Kubernetes client libraries.
- Kubernetes and Helm baseline.
- KubeRay operator/chart.
- Prometheus stack/chart.
- KEDA and KEDA HTTP Add-on.
- NVIDIA Device Plugin.
- Baseline model revision.

Never commit `latest`. If the agent must discover current stable versions, it must document the official source and compatibility decision before pinning them.

### Phase 0 gate

Phase 0 passes only when:

- The selected profile is explicit.
- Preflight passes on the actual target host.
- The machine-readable report is generated.
- The benchmark workload and SLO are documented without ambiguous “tokens/sec” language.
- All runtime, model, chart, and test dependencies have exact pins.
- Unit tests pass.

Stop after reporting evidence and request approval for Phase 1.

## 12. Phase 1 — Local containerized vLLM baseline

### Objective

Serve the pinned baseline model from one complete Dockerized inference replica and prove concurrent streaming behavior.

### Dockerfile requirements

- Build from the pinned official `vllm/vllm-openai` image.
- Prefer a thin wrapper; do not rebuild CUDA or vLLM from source without a demonstrated requirement.
- Do not include secrets or model weights.
- Add only pinned dependencies that are required inside the server image.
- Preserve or document the upstream entrypoint behavior.
- Add OCI labels for source revision and build metadata when practical.

### Compose requirements

`docker/compose.yaml` must configure:

- NVIDIA GPU allocation.
- Port 8000 or the configured host port.
- A persistent model/Hugging Face cache.
- Explicit shared-memory capacity, using one reviewed strategy such as `shm_size` or host IPC.
- A server health check.
- A deterministic container name or labels suitable for diagnostics.
- A clear restart policy that does not hide crashes from tests.
- Environment-driven model and engine arguments.
- Read-only mounts where possible.
- No plaintext secret values in the committed file.

### Initial engine configuration

Use conservative, documented values for:

- Maximum model length.
- GPU memory utilization.
- Maximum concurrent sequences.
- Served model name.
- Host binding.
- API key, if enabled.

The server must expose:

- The OpenAI-compatible API under `/v1`.
- A health endpoint supported by the pinned vLLM version.
- The Prometheus-compatible `/metrics` endpoint.

### `tests/test_phase1.py`

The test must:

1. Wait for service readiness using a bounded deadline.
2. Query the model-list endpoint and validate the served alias.
3. Send exactly ten concurrent chat-completion requests with streaming enabled.
4. Consume every server-sent event or streaming chunk through the terminal event.
5. Validate HTTP status, chunk structure, non-empty generated content, terminal completion, and elapsed-time bounds.
6. Record per-request TTFT, end-to-end latency, output text length, and status.
7. Fail if any request errors, times out, produces malformed output, or ends without a terminal event.
8. Inspect the container after the run and fail on OOM, unhealthy status, unexpected exit, or restart.
9. Save an ignored JSON report under `artifacts/phase1/`.

Use deterministic prompts and conservative output limits. Content quality evaluation is not part of this smoke test.

### `tests/benchmark_phase1.py`

The benchmark must:

- Read the workload contract rather than burying parameters in code.
- Support configurable concurrency and duration.
- Warm the engine before measurement.
- Tokenize using the pinned model tokenizer or use validated server usage counts.
- Record raw per-request data.
- Report input/output tokens/sec separately.
- Report request rate, latency percentiles, errors, and timeouts.
- Query vLLM metrics before, during, and after the run when available.
- Include the effective non-secret server configuration and hardware report.
- Never silently discard failed requests from denominator calculations.

### Phase 1 gate

Phase 1 passes only when:

- Ten concurrent streams complete with zero failures.
- Health, model-list, and metrics endpoints respond.
- The server has no OOM, crash, or restart.
- Benchmark artifacts are reproducible and include raw data.
- README instructions reproduce the result from a clean checkout with the same host prerequisites.

Performance targets are reported, but Phase 1 must not fail merely because an aspirational 5,000 output-tokens/sec goal was unrealistic for the selected hardware unless that number was explicitly made a hard Phase 1 SLO.

## 13. Phase 2 — Multi-GPU and Ray validation

### Objective

Prove same-host TP and, where real multi-node hardware is available, prove a genuine distributed Ray topology.

### Phase 2A — Same-host TP with multiprocessing

Requirements:

- Require two physical GPUs in preflight.
- Start one complete inference replica with `tensor_parallel_size=2` and the native multiprocessing backend.
- Use sufficient shared memory.
- Capture GPU topology and interconnect information.
- Verify both GPU worker processes start.
- Verify both GPUs allocate meaningful model memory.
- Do not require exact memory equality because rank-specific contexts and API overhead differ.
- Compare results with the single-GPU baseline.
- Document whether TP improves or reduces TTFT, throughput, and memory headroom for this model.

### Phase 2A — Ray backend compatibility

Requirements:

- Install the pinned Ray dependency compatible with the pinned vLLM image.
- Start a bounded local Ray cluster.
- Force the Ray distributed executor.
- Prove that vLLM creates the expected Ray workers and GPU placement.
- Expose Ray diagnostics without exposing credentials.
- Cleanly stop the local Ray cluster through documented commands.

This proves backend compatibility, not genuine multi-node operation.

### Phase 2B — True multi-node Ray

Run this subphase only when at least two physical GPU nodes are available. Otherwise mark it `NOT RUN — HARDWARE UNAVAILABLE`; do not fake a pass.

Requirements:

- Use the identical immutable server image on every node.
- Use the same immutable model snapshot path on every node.
- Verify compatible NVIDIA drivers, CUDA runtime, networking, and GPU resources.
- Configure the Ray head and workers explicitly.
- Set node and host-address environment values required by vLLM/Ray.
- Validate required ports and firewall rules.
- Capture Ray cluster resources and placement groups.
- Begin with TP within each node and PP across nodes unless the selected topology requires otherwise.
- Record NCCL interface selection and diagnostics.
- Do not assume consumer Ethernet provides acceptable cross-node TP performance.

### `tests/test_phase2.py`

The test must:

- Rerun all Phase 1 functional assertions.
- Query Ray status and validate expected live nodes and GPU resources.
- Validate expected vLLM worker count and topology.
- Validate that every intended GPU has a model allocation within a reasonable tolerance.
- Detect fallback to fewer GPUs.
- Capture logs relevant to NCCL and Ray placement.
- Fail on worker death, placement timeout, NCCL timeout, API mismatch, OOM, or stream failure.
- Produce a topology and benchmark comparison artifact.

An optional resilience test may terminate a Ray worker. Its expected outcome must be defined in advance: either automated recovery within a deadline or a clear failed/unready service. Silent partial service is unacceptable.

### Phase 2 gate

Phase 2A passes only with real two-GPU evidence and API parity. Phase 2B has its own gate and cannot pass without real multi-node hardware. The project may proceed to the Kubernetes single-replica profile after Phase 2A even when Phase 2B is intentionally deferred.

## 14. Phase 3 — Kubernetes deployment

### Objective

Deploy a complete inference replica into a GPU-enabled Kubernetes cluster with deterministic model storage and safe lifecycle behavior.

### Cluster prerequisites

Document and validate:

- Kubernetes and Helm versions.
- NVIDIA driver and container runtime on GPU nodes.
- NVIDIA Device Plugin installation.
- `nvidia.com/gpu` capacity reported by the nodes.
- StorageClass and access modes.
- Ingress or Gateway choice, if enabled.
- Prometheus Operator CRDs if a ServiceMonitor will be installed later.

Treat the NVIDIA Device Plugin as cluster infrastructure. Provide pinned installation instructions and a small GPU validation workload, but do not hide cluster-wide installation inside an application deployment command.

### `k8s-replica` base resources

Create, as appropriate:

- Namespace.
- ServiceAccount with minimal permissions.
- ConfigMap for non-secret model/server settings.
- Secret reference or example manifest with placeholder data only.
- PVC or documented node-local model cache.
- Versioned model-download Job.
- vLLM Deployment.
- ClusterIP Service.
- PodDisruptionBudget.
- NetworkPolicy where supported.
- Optional ingress/gateway resources in overlays.

### GPU scheduling

- Request the exact number of GPUs required by the replica using `nvidia.com/gpu` limits.
- Make the relationship `GPUs per pod = tensor_parallel_size × pipeline_parallel_size` explicit for a self-contained single-pod replica, unless a documented vLLM topology says otherwise.
- Use node selectors, affinity, and tolerations through overlays rather than hard-coding cloud-specific labels in the base.
- Do not use GPU time-slicing for tensor-parallel ranks unless explicitly designed and benchmarked.
- Avoid a rolling update strategy that deadlocks because no spare GPU capacity exists. Use `Recreate` in constrained local environments; use a controlled rolling strategy only when the production cluster reserves sufficient spare GPUs.

### Model storage and download behavior

- Download an exact model revision into a revision-specific directory.
- Prefer a standalone Job over every serving pod racing to download the same snapshot.
- Download into a temporary versioned location and publish a completion marker only after validation succeeds.
- Record model metadata and file checksums where practical.
- Mount completed weights read-only into vLLM pods.
- Start vLLM from the local snapshot path, not from an unpinned remote identifier.
- Configure serving pods so a restart can succeed without model-registry network access.
- For multiple nodes, explicitly choose:
  - RWX storage with measured throughput, or
  - A controlled node-local cache populated from immutable object storage.

A generic PVC does not automatically provide cross-node sharing. Document the selected StorageClass and access mode.

### Probes and lifecycle

- Use a startup probe with enough time for model loading and CUDA initialization.
- Do not let liveness kill the pod during normal model startup.
- Use readiness to exclude the pod until the API and model are usable.
- Use a conservative liveness probe that detects a truly wedged server.
- Configure termination grace long enough for the maximum allowed generation.
- Emit useful termination and startup diagnostics.

### Kubernetes overlays

- `local`: constrained GPU capacity, local storage choice, and a safe update strategy.
- `eks`: GPU node labels/tolerations, storage, load balancer/ingress, and IAM integration placeholders.
- `gke`: GPU node labels/tolerations, storage, load balancer/gateway, and workload identity placeholders.

Cloud overlays must remain examples until tested in their actual cloud environments. Never claim an untested overlay is validated.

### `k8s-ray-multinode` resources

For the advanced profile:

- Install the pinned KubeRay operator separately.
- Define a RayCluster or RayService with explicit head and worker resources.
- Use identical images and model paths.
- Configure shared-memory capacity for every participating pod.
- Apply GPU resources to the correct head/worker groups.
- Define TP/PP topology explicitly.
- Validate cluster and Serve application status.

Do not attach the Phase 4 KEDA Deployment scaler to individual KubeRay workers. Horizontal scaling of complete distributed Ray replicas is outside the MVP unless a controller that owns whole replicas is explicitly designed and tested.

### `tests/test_phase3.py`

The test must:

1. Validate manifests or rendered templates locally.
2. Verify required CRDs before applying dependent resources.
3. Wait for the model-download Job and verify its completion marker.
4. Wait for rollout and readiness with bounded timeouts.
5. Verify requested GPUs appear in pod resources and server diagnostics.
6. Port-forward or use the configured route and rerun Phase 1 streaming assertions.
7. Delete or restart a serving pod.
8. Prove the replacement starts from cached weights without external model access, ideally by denying serving-pod egress to the model registry or otherwise capturing deterministic evidence.
9. Fail on download repetition, probe loops, OOM, restart loops, or API failure.

### Phase 3 gate

The selected Kubernetes profile must deploy cleanly, allocate the intended GPUs, become ready, serve concurrent streaming requests, and restart from immutable cached weights. All generated manifests must be reproducible from the committed configuration.

## 15. Phase 4 — Observability and autoscaling

### Objective

Observe service behavior and scale complete inference replicas using a demand signal that remains semantically valid for the selected minimum replica count.

### Prometheus integration

Install or integrate with a pinned Prometheus stack. Provide:

- Service annotations or, preferably, a ServiceMonitor when the Prometheus Operator is present.
- Stable labels for environment, model alias, replica, and pod.
- A recording/query guide for:
  - `vllm:num_requests_running`
  - `vllm:num_requests_waiting`
  - `vllm:kv_cache_usage_perc`
  - `vllm:prompt_tokens_total`
  - `vllm:generation_tokens_total`
  - `vllm:time_to_first_token_seconds`
  - `vllm:inter_token_latency_seconds`
  - `vllm:e2e_request_latency_seconds`
  - HTTP request/error metrics available in the pinned version
- GPU metrics through DCGM Exporter or an explicitly approved equivalent for production monitoring.
- A dashboard or documented queries covering demand, throughput, latency, cache pressure, GPU utilization, errors, and restarts.

Verify actual metric names from the pinned vLLM image. Do not assume names remain identical across versions.

Example PromQL patterns, to be adjusted for actual labels:

```promql
sum(vllm:num_requests_waiting)
```

```promql
sum(rate(vllm:generation_tokens_total[5m]))
```

```promql
histogram_quantile(
  0.95,
  sum by (le) (rate(vllm:time_to_first_token_seconds_bucket[5m]))
)
```

### Phase 4A — One warm replica

Create a KEDA ScaledObject targeting only the standard vLLM Deployment:

- `minReplicaCount: 1`.
- A measured and documented `maxReplicaCount` constrained by available GPUs.
- Scale primarily from aggregate waiting requests.
- Treat running requests and KV-cache utilization as observability and safety/capacity-tuning signals, not the sole activation metric.
- Return a scalar even when no waiting-request series exists, for example through a reviewed PromQL zero fallback.
- Tune threshold from measured per-replica capacity, not an arbitrary number copied from an example.
- Configure aggressive-enough scale-up and conservative scale-down.
- Add a scale-down stabilization window and long cooldown to avoid repeatedly unloading expensive models.
- Ensure cluster GPU capacity or node autoscaling can satisfy the maximum before advertising it.

KEDA cannot manufacture GPU nodes. Pending inference pods must be surfaced as an alert and a failed scaling objective.

### Graceful streaming drain

Graceful drain is a prerequisite for the Phase 4 “no dropped streams” gate, not deferred hardening.

Implement and document an explicit strategy that:

1. Stops sending new requests to a terminating replica.
2. Allows endpoint removal to propagate.
3. Tracks or bounds in-flight requests.
4. Gives active streams time to finish.
5. Terminates only after drain completion or a documented maximum deadline.

Use a gateway/proxy with drain awareness where practical. A fixed pre-stop delay alone is only a fallback and must be longer than endpoint propagation plus the permitted request duration. Configure `terminationGracePeriodSeconds`, rollout behavior, PodDisruptionBudget, and KEDA stabilization consistently.

### Phase 4B — True HTTP scale-to-zero

Enable only after Phase 4A passes.

- Install the pinned KEDA HTTP Add-on.
- Place the interceptor in front of vLLM.
- Route every relevant external request through the interceptor rather than directly to the backend Service.
- Scale on interceptor concurrency, request rate, or both.
- Configure `minReplicaCount: 0` only for this profile.
- Set readiness and total request timeouts based on measured model-load time.
- Define whether cold-start requests are held, receive a placeholder response, or use a fallback service.
- Expose cold-start behavior to clients and operations documentation.
- Test OpenAI-compatible streaming through the interceptor.
- Document that scale-to-zero trades GPU cost for potentially long cold-start latency.

Do not claim scale-to-zero from a Prometheus metric emitted only by vLLM.

### `tests/load_phase4.py`

The load generator must:

- Support stepped and burst concurrency patterns.
- Use streaming completions.
- Use a bounded, documented prompt/output distribution.
- Measure client-side TTFT, completion latency, success, timeouts, and disconnects.
- Preserve every attempted request in raw results.
- Expose load stages that can be correlated with metrics and replica changes.

Suggested stages:

1. Idle baseline.
2. Warm-up.
3. Load below one-replica capacity.
4. Sustained load above threshold.
5. Burst load.
6. Recovery and idle cooldown.
7. Optional activation from zero.

### `tests/watch_scaling.py`

The watcher must record, with timestamps:

- Offered concurrency/rate.
- Running and waiting vLLM requests.
- Desired, current, available, and ready replicas.
- Pending/unschedulable pods.
- KEDA and HPA conditions.
- Pod readiness transitions.
- Cold-start duration.
- Stream failures.
- Scale-out and scale-in times.

### Phase 4 gate

Run the test at least three times. It passes only when:

- Demand causes the expected scale-out.
- New replicas become ready and receive traffic.
- No active stream is dropped during controlled scale-down.
- The service returns to its configured minimum after cooldown.
- No pod OOMs or enters a restart loop.
- Any unschedulable GPU capacity is reported as failure, not as successful autoscaling.
- For the zero profile, a request arriving at zero activates a replica and completes according to the documented cold-start contract.

## 16. Phase 5 — Production hardening

### Objective

Close security, resilience, operational, and cloud-deployment gaps before calling the platform production-ready.

### Security

- Require API authentication at the gateway or server.
- Apply request-size, prompt-length, output-length, concurrency, and rate limits.
- Store secrets in Kubernetes Secrets or an approved external secret manager.
- Use minimal service accounts and RBAC.
- Apply NetworkPolicies.
- Run with the least privilege supported by the GPU stack.
- Use read-only root filesystems and drop Linux capabilities where compatible.
- Review any use of `trust_remote_code`.
- Generate an SBOM and scan server/application images.
- Record model license and provenance.
- Pin and verify model revisions and container digests.

### Reliability

- Test node loss, pod eviction, failed model download, corrupt cache marker, and unavailable GPU.
- Test gateway, Prometheus, KEDA, and Ray component failures relevant to the selected profile.
- Define failure behavior when no GPU capacity remains.
- Test rolling updates and rollback.
- Verify graceful draining during deployment changes and node maintenance.
- Run a sustained 30–60 minute workload at the documented operating envelope with no OOM or unbounded queue growth.
- Create alerts for errors, pending pods, queue depth, high TTFT, KV-cache pressure, GPU faults, and restart loops.

### Operations

`docs/operations.md` must include:

- Startup, shutdown, and health verification.
- Model-version rollout and rollback.
- Cache population and repair.
- Capacity and quota checks.
- Scaling behavior and cold starts.
- Common alerts and response steps.
- Diagnostic collection.
- Ray recovery for the multi-node profile.
- Safe removal of a GPU node.
- Known limits and unsupported configurations.

`docs/troubleshooting.md` must cover:

- CUDA or NVIDIA runtime not visible.
- Insufficient `nvidia.com/gpu` capacity.
- Model download/authentication failures.
- OOM during startup or load.
- Shared-memory exhaustion.
- NCCL or Ray placement timeouts.
- Startup/readiness/liveness probe failures.
- Metrics not scraped.
- KEDA not scaling.
- Pods pending after scale-out.
- Streams dropped during shutdown.
- Cold-start timeout from zero.

### Capacity and cost model

Document:

- GPUs required per complete replica.
- Measured per-replica throughput at each workload profile.
- Maximum safe concurrency.
- Model-load and cold-start times.
- Storage footprint and download bandwidth.
- Idle and loaded GPU cost.
- Scale-out lead time.
- Minimum warm capacity needed for the latency SLO.

### Phase 5 gate

Production readiness requires passing the sustained load test, failure tests, rolling update/rollback, security checks, alert verification, and operator documentation review in the actual target environment.

## 17. Test architecture

Use pytest markers or an equivalent clear taxonomy:

- `unit`: no Docker, GPU, network, or cluster required.
- `docker`: requires local Docker.
- `gpu`: requires physical NVIDIA GPU access.
- `ray`: requires the documented Ray topology.
- `k8s`: requires the selected Kubernetes context.
- `load`: creates significant serving load.
- `cloud`: requires explicit cloud credentials and approval.

Rules:

- A default unit-test command must not unexpectedly allocate GPUs or modify a cluster.
- Destructive or expensive tests require an explicit flag/profile.
- All waits have deadlines and diagnostic output.
- Tests clean up only the resources they created.
- Tests never use broad namespace or cluster deletion.
- Raw results go under ignored `artifacts/` directories.
- CI validates Python, formatting, unit tests, YAML syntax, Kubernetes schemas, Helm/Kustomize rendering, and secret scanning without requiring a GPU.
- GPU, Kubernetes, Ray, and load suites run as separately labeled integration jobs on suitable infrastructure.

## 18. Command interface

Expose a predictable operator interface through the Makefile or an equivalent task runner. Suggested targets:

```text
make help
make setup
make lint
make test-unit
make preflight PROFILE=local-1gpu
make phase1-build
make phase1-up
make test-phase1
make benchmark-phase1
make phase1-down
make phase2-up PROFILE=local-2gpu-mp
make test-phase2 PROFILE=local-2gpu-mp
make k8s-render OVERLAY=local
make k8s-apply OVERLAY=local
make test-phase3 OVERLAY=local
make observability-apply
make test-phase4
make diagnostics
```

Every target must be documented, non-interactive where practical, and safe to rerun. Teardown targets must use explicit project names, namespaces, or labels and must not delete unrelated user resources.

## 19. Acceptance matrix

| Capability | Evidence required |
|---|---|
| Local API serving | Health/model/metrics endpoints plus 10 successful concurrent streams |
| No baseline OOM | Container remains healthy with zero restarts and no OOM evidence |
| Reproducible benchmark | Contract, raw results, hardware/config snapshot, and percentile summary |
| Same-host TP | Two real GPUs, correct worker topology, both GPUs allocated, API parity |
| Ray compatibility | Ray nodes/resources/placement evidence plus API parity |
| True multi-node | At least two real physical GPU nodes and documented TP/PP topology |
| Kubernetes GPU scheduling | Pod resource allocation plus runtime GPU evidence |
| Cached restart | Serving pod restarts without remote model retrieval |
| Metrics | Prometheus queries return expected vLLM and GPU series |
| Warm autoscaling | Repeated scale-out/in with no dropped streams or unschedulable success claims |
| Scale-to-zero | Persistent interceptor activates from zero and request completes under cold-start contract |
| Production readiness | Sustained load, resilience, upgrade/rollback, security, alerting, and runbooks all verified |

## 20. Risk register

| Risk | Impact | Required mitigation |
|---|---|---|
| “5,000 tokens/sec” is underspecified | False success or impossible target | Freeze exact workload and hardware in Phase 0 |
| Small AWQ model gives misleading TP results | Bad topology decision | Treat it as functional; benchmark a representative second model |
| Consumer GPUs have slow cross-GPU/network links | TP/PP overhead and poor latency | Measure topology; prefer TP within node and PP across nodes |
| Model cache is assumed to be shared | Re-downloads or inconsistent files | Pin revision, choose RWX or node-local strategy, publish completion marker |
| Multiple pods race to download weights | Corruption and wasted bandwidth | Use a dedicated versioned download Job |
| vLLM metric names change | Broken dashboards/scaling | Verify names against pinned image and test Prometheus queries |
| Scaling on running requests alone | Delayed or misleading capacity response | Scale primarily on waiting work or gateway concurrency |
| Scale-to-zero loses activation signal | Service never wakes | Keep a persistent HTTP interceptor/gateway |
| LLM cold start exceeds proxy timeout | Failed first request | Measure startup and configure explicit cold-start policy |
| HPA terminates streaming pods | Dropped responses | Implement drain strategy, stabilization, PDB, and termination grace |
| KEDA requests more pods than GPUs | Pending pods and no added capacity | Cap replicas, integrate node scaling, and alert on unschedulable pods |
| Ray workers are scaled independently | Broken model replica | Keep complete TP/PP topology under one controller |
| Rolling update requires unavailable spare GPUs | Deployment deadlock | Use Recreate locally or reserve production surge capacity |
| Floating images/models change behavior | Non-reproducible results | Pin image digests and model revisions |
| Secrets enter Compose/YAML/logs | Credential compromise | Use placeholders, secret stores, redaction, and secret scanning |

## 21. Definition of done

The complete project is done only when:

- Every selected deployment profile has explicit prerequisites and a reproducible command path.
- Phase gates have real evidence from the required hardware; deferred profiles are labeled honestly.
- The OpenAI-compatible streaming API behaves correctly under concurrency.
- Performance claims distinguish input tokens, output tokens, request rate, TTFT, and end-to-end latency.
- The documented workload envelope produces no OOM or restart loop.
- Complete inference replicas scale horizontally without corrupting TP/PP topology.
- Kubernetes restarts use immutable cached weights.
- Metrics, dashboards, KEDA, and alerts are validated.
- Controlled scale-down does not drop active streams.
- Scale-to-zero, if enabled, uses a persistent activation signal and an explicit cold-start contract.
- Security, rollback, failure recovery, capacity, and troubleshooting documentation are complete.
- No training or fine-tuning code exists.
- No credential, unpinned production image, or unpinned model revision is committed.

## 22. Required Phase 0 questions

Before implementation, discover what can be determined automatically and ask only for choices that materially affect the result:

1. Which initial profile should be implemented: `local-1gpu`, `local-2gpu-mp`, or another explicit profile?
2. What NVIDIA GPU model(s), count, and VRAM are available?
3. Is the host Linux with a working NVIDIA container runtime?
4. Which local Kubernetes environment will be used, if any?
5. Are there at least two physical GPU nodes for the multi-node Ray profile?
6. Which cloud target is real: EKS, GKE, both, or neither for the first release?
7. Is the 5,000 output-tokens/sec figure a hard SLO or an aspirational benchmark?
8. What prompt/output length and concurrency describe the expected production workload?
9. Is scale-to-zero mandatory despite model cold-start latency, or is one warm replica acceptable?
10. Is API authentication required in the local MVP or only in production overlays?

If these answers are unavailable, choose only reversible defaults for Phase 0, document them as assumptions, and do not claim hardware-specific gates have passed.

## 23. Official technical references

- [vLLM Docker deployment](https://docs.vllm.ai/en/stable/deployment/docker/)
- [vLLM parallelism and scaling](https://docs.vllm.ai/en/stable/serving/parallelism_scaling/)
- [vLLM Kubernetes deployment](https://docs.vllm.ai/en/stable/deployment/k8s/)
- [vLLM metrics](https://docs.vllm.ai/en/latest/design/metrics/)
- [vLLM quantization support](https://docs.vllm.ai/en/stable/features/quantization/)
- [Ray on Kubernetes and KubeRay](https://docs.ray.io/en/latest/cluster/kubernetes/index.html)
- [RayService quickstart](https://docs.ray.io/en/latest/cluster/kubernetes/getting-started/rayservice-quick-start.html)
- [NVIDIA Kubernetes Device Plugin](https://github.com/NVIDIA/k8s-device-plugin)
- [KEDA Prometheus scaler](https://keda.sh/docs/latest/scalers/prometheus/)
- [KEDA HTTP Add-on](https://keda.sh/http-add-on/)

## 24. First response expected from the coding agent

The coding agent must respond with:

1. A concise acknowledgement that it has read the full blueprint.
2. A correct explanation that TP/PP form one complete model replica, while KEDA adds or removes complete replicas.
3. A statement that vLLM-only metrics cannot wake a zero-replica service and that a persistent gateway/interceptor is required.
4. The Phase 0 facts it can inspect automatically.
5. Only the unresolved Phase 0 questions that materially block a correct hardware and benchmark contract.
6. A request for permission to begin Phase 0.

It must not create implementation files before receiving that permission.
