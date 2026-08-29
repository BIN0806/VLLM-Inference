# Feature pathway

This pathway shows how to adopt the platform one capability at a time. Each
stage is useful by itself; a personal deployment does not need Kubernetes or
autoscaling unless those features solve a real problem.

```text
offline authoring
  -> single-GPU Compose
    -> larger model with TP/Ray
      -> one Kubernetes replica
        -> Prometheus
          -> KEDA 1→2
            -> HTTP scale-to-zero
              -> production hardening goals
```

| Stage | Capability | Best use | Cost/complexity |
|---|---|---|---|
| 0 | Offline profiles, tests, and rendering | Learn or change the project safely | No GPU cost |
| 1 | One 1.5B AWQ Compose container | Personal API, experiments, portfolio demos | Lowest live cost |
| 2 | 9B TP=2 with native `mp` or Ray | Learn model-fit and distributed execution | Two GPUs |
| 3 | One k3s GPU replica | Learn scheduling, probes, Services, and PVCs | One GPU VM |
| 4 | Prometheus scrape | Understand queue, tokens, KV cache, and latency | Modest RAM/disk overhead |
| 5 | KEDA 1→2→1 | Add request capacity under queued load | Two schedulable GPUs |
| 6 | HTTP interceptor 0→1→0 | Remove idle model GPU usage while retaining a front door | Minutes of cold-start latency |
| 7 | Production goals | Public, resilient, multi-node service | Provider and operations investment |

## Stage 0: authoring and offline validation

**Goal:** change profiles, manifests, or clients without renting a GPU.

```bash
uv sync --python 3.12 --extra dev
make lint
make test-unit
make preflight PROFILE=authoring
make k8s-render K8S_PROFILE=vast-k3s-replica
make k8s-render-replicas PHASE4_PROFILE=vast-k3s-replicas
```

The authoring Mac is not a CUDA gate. GPU, Ray, and cluster checks remain
separate and explicit.

**Move on when:** offline tests pass and the selected model/topology contract is
clear.

## Stage 1: personal single-GPU service

**Goal:** expose one private OpenAI-compatible vLLM endpoint through loopback
and SSH.

Use the pinned 1.5B AWQ profile first:

- profile: `vast-k3s-replica`;
- model: `Qwen/Qwen2.5-1.5B-Instruct-AWQ`;
- topology: TP=1, one container, one GPU;
- access: remote `127.0.0.1:8000` plus an SSH local forward.

Repository entry points:

```bash
make compose-env-check PROFILE=vast-k3s-replica
make phase1-build PHASE1_PROFILE=vast-k3s-replica
make phase1-up PHASE1_PROFILE=vast-k3s-replica
make health
INFERENCE_PROFILE=vast-k3s-replica make test-phase1
make phase1-down PHASE1_PROFILE=vast-k3s-replica
```

See [Personal use](personal-use.md) for the complete workflow.

**Move on when:** health, model discovery, metrics, and concurrent SSE pass;
shutdown removes the listener and GPU process.

## Stage 2: larger-model fit and distributed execution

**Goal:** run one model replica whose execution spans two GPUs.

- Start with native multiprocessing and TP=2.
- Record GPU topology before drawing performance conclusions.
- Repeat the same model, revision, serving flags, and workload with same-host
  Ray only if executor behavior is the question.
- Keep both paths as one replica; do not describe TP ranks as independent
  capacity.

The accepted project used Qwen3.5-9B on two 12 GiB RTX 3060 GPUs. That hardware
proved fit and correctness but is not a recommended performance target.

**Move on when:** both ranks are visible, health and SSE pass, and the benchmark
records memory/topology without silent fallback.

## Stage 3: one Kubernetes replica

**Goal:** move lifecycle ownership from Compose to Kubernetes.

Features:

- single-node k3s;
- NVIDIA RuntimeClass and device plugin;
- `nvidia.com/gpu: 1` request;
- startup, readiness, and liveness probes;
- ClusterIP Service;
- model-cache PVC;
- `enableServiceLinks: false`.

Use the Phase 3 runbooks and render targets. Do not apply manifests until the
VM passes read-only preflight.

**Move on when:** the pod becomes Ready, streaming passes, pod replacement
recovers, and the cache marker survives on the same VM.

## Stage 4: observe before scaling

**Goal:** prove the exact metrics and labels exported by the pinned vLLM
release.

Install the trimmed Prometheus profile, then verify:

- the ServiceMonitor target is up;
- prompt/generation token totals move;
- running and waiting requests move under load;
- KV-cache and latency series exist;
- histogram counts and sums use aligned windows.

**Move on when:** the intended KEDA query returns one scalar based on live
series rather than guessed names.

## Stage 5: warm horizontal capacity

**Goal:** add a second complete one-GPU replica when the first has queued work.

The accepted scaler uses:

- `sum(vllm:num_requests_waiting)`;
- KEDA `metricType: Value`;
- min=1, max=2;
- one per-ordinal PVC;
- a scale-down stabilization window.

Prove distribution with an in-cluster client against the ClusterIP Service and
a new TCP connection per request. A port-forward can stay sticky to one pod.

**Move on when:** both per-pod counters move, aggregate throughput increases,
and automatic scale-down leaves GPU 1 idle and PVC 1 retained.

## Stage 6: scale-to-zero

**Goal:** allow vLLM replicas to reach zero while retaining a process that can
observe and hold new requests.

Use the KEDA HTTP interceptor and exactly one ScaledObject/HPA for the vLLM
StatefulSet. Client and interceptor timeouts must exceed measured model startup.

The completed gate exercised interceptor-driven 0→1 and later 1→0. It kept the
original request, returned valid streaming output, and reused the ordinal PVC.

**Move on when:** zero-state GPUs are idle, vLLM metrics are absent,
interceptor metrics remain, one non-retried request completes after activation,
and normal scale-down returns to zero.

## Stage 7: goals

- Exercise interceptor-driven 0→2 with retained client logs and error rates.
- Add authenticated TLS ingress and multiple interceptor replicas.
- Move model distribution to provider-persistent or object-backed storage.
- Add multi-node Kubernetes, anti-affinity, disruption budgets, alerts, and
  node-failure tests.
- Extend Ray/KubeRay across physical GPU nodes.
- Autoscale independent 9B replicas on GPUs with adequate TP=1 headroom.
- Freeze a production workload and evaluate the hardware/cost required for
  5,000 output tokens/s.

These goals extend the completed single-node lab; they are not required for a
useful personal deployment.

## Choosing the right stopping point

| Need | Stop at |
|---|---|
| Private personal chat/completion API | Stage 1 |
| Learn multi-GPU model fit | Stage 2 |
| Learn Kubernetes GPU operations | Stage 3 |
| Build dashboards and capacity evidence | Stage 4 |
| Handle bursts across two GPUs | Stage 5 |
| Avoid paying for an idle model process | Stage 6 |
| Operate a public resilient service | Stage 7 goals |

Prefer the simplest stage that meets the actual need. Every extra control plane
adds memory use, cold-start behavior, failure modes, and operational work.
