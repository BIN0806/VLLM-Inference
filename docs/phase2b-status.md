# Phase 2B gate status

Recorded from the macOS authoring workstation. CUDA/vLLM ran on the **same**
two-GPU Vast rental as Phase 2A. Executor backend is **Ray** on **one physical
host**. Multi-node Ray, Kubernetes, Prometheus-as-a-stack, and KEDA were
**not** started. The instance was **not** destroyed.

SSH-tunneled tests hit vLLM on remote loopback only. No public vLLM endpoint
was opened. Hosts, tokens, and fingerprints are not published.

Phase 2B is compared **directly to Phase 2A** (same host, model, topology,
context, concurrency, and compatibility flags). Percentage deltas do **not**
imply that Ray must be faster than native `mp`.

## Gate decision: **GO for Phase 2B (same-host Ray)**. **STOP.**

Do not begin multi-node Ray, Kubernetes, Prometheus installation, or KEDA.
Do not destroy the instance until this report is committed, pushed, and
explicitly approved.

## Git / tag before replacement

- `phase-2` was clean and matched `origin/phase-2` at
  `5caf24b0d3a81ee0e769442716d9d1fcd1472eac`.
- Annotated tag `phase2a-vast-2x3060-tp2-pass` points at that commit and was
  pushed.

## Phase 2A process captured, then stopped

Final native `mp` evidence (sanitized):

- Command: `vllm serve` local snapshot, `--distributed-executor-backend mp`,
  TP=2, PP=1, `--max-model-len 8192`, `--max-num-seqs 2`,
  `--gpu-memory-utilization 0.90`, `--enforce-eager`,
  `--disable-custom-all-reduce`, `--skip-mm-profiling`,
  `--limit-mm-per-prompt {"image":0,"video":0}`, bind remote loopback.
- PIDs: API server 8025, EngineCore 8324, Worker_TP0 8468, Worker_TP1 8469.
- `/health` HTTP 200; live model `Qwen/Qwen3.5-9B`; `/metrics` 52508 bytes.
- GPUs: 10643 MiB used on each RTX 3060 (workers 10634 MiB each).
- Listen: remote `127.0.0.1:18000` only.

The local SSH API tunnel targeted only workstation loopback
(`localhost` → remote loopback). It was closed with SIGTERM before replacement
(local port 8000 became free). It could not expose the GPU host publicly.

Graceful stop: SIGTERM to process group 8025. **SIGKILL was not used.** After
stop: port 18000 free; API/EngineCore/TP0/TP1 gone; GPUs ~1 MiB; snapshot and
cache symlinks intact; disk 5.22 GiB free.

## Ray cluster (read-only, then reused)

Template Supervisor program `ray` was **RUNNING** (`/opt/supervisor-scripts/ray.sh`).
Host env `RAY_ADDRESS` was an IP without a port (invalid for the Ray CLI).
Connecting to **loopback GCS** `127.0.0.1:6379` succeeded.

| Fact | Observed |
|---|---|
| Ray version | 2.58.0 |
| Address used | `127.0.0.1:6379` |
| Physical nodes | **1** (head, ALIVE) |
| GPU resources | **2.0** total, **2.0** available before vLLM |
| Logical CPU | 15.0 |
| Actors before start | none |
| Placement groups before start | none |
| Dashboard | template binds dashboard on the node IP port 28265; Caddy also listens on 8265. We did not add a public mapping. vLLM connected via loopback GCS. |

Startup configuration (template, documented not rewritten): `ray start --head`
with `--port 6379`, pinned manager/object/dashboard-agent ports in 6379–6385,
worker ports 6390–6499, `--dashboard-host` set to the node address,
`--dashboard-port 28265`. This is **one host**. It is not multi-node.

No stale vLLM actors or placement groups were present, so none were removed.
The existing cluster was healthy and empty, so it was **reused**. A new Ray
head was not started.

## Live Phase 2B configuration

Identical to the successful Phase 2A serving flags except the executor:

| Setting | Value |
|---|---|
| Model | `Qwen/Qwen3.5-9B` |
| Revision | `c202236235762e1c871ad0ccb60c8ee5ba337b9a` |
| Tensor parallel | 2 |
| Pipeline parallel | 1 |
| Executor | **`ray`** |
| Max model length | 8192 |
| Max sequences | 2 |
| GPU memory utilization | 0.90 |
| Eager | `--enforce-eager` |
| MM | `--skip-mm-profiling`, `image=0,video=0` |
| CUDA devices | 0 and 1 |
| Offline | `HF_HUB_OFFLINE=1`, `HF_HUB_DISABLE_XET=1` |
| Bind | remote `127.0.0.1:18000` only |
| Cache | existing local snapshot; no download |
| Allreduce | `--disable-custom-all-reduce` (no P2P, same as 2A) |

No model fallback. `NCCL_P2P_DISABLE` was not set. No retry beyond the single
successful Ray start.

## Acceptance

| Check | Result |
|---|---|
| `GET /health` | HTTP **200** |
| `GET /v1/models` | `Qwen/Qwen3.5-9B`, `max_model_len` 8192 |
| Executor logs | `--distributed-executor-backend ray`; connected to existing Ray cluster; **created a placement group**; workers are `RayWorkerProc` (`Worker_TP0` / `Worker_TP1`). **No `multiproc_executor` in the Phase 2B log.** |
| Ray after load | 1 node; 2.0/2.0 GPU used (reserved in placement groups); actors `vllm_Worker_*_TP0` and `_TP1` (`RayWorkerProc`, ALIVE); one CREATED placement group |
| GPU ranks | `ray::RayWorkerProc.run` 10766 MiB on GPU0 and 10766 MiB on GPU1 (10775 MiB used per card) |
| Ten concurrent SSE | 10/10 `ok`, non-empty, `data: [DONE]` (pytest 2 passed in 44.82 s) |
| `/metrics` | tunneled Prometheus text, HTTP 200, 52454 bytes |
| Benchmark | identical 30 s warm-up + 60 s measurement, 20/20 ok, 0 errors |
| Disk | 5.21 GiB free after load (fail threshold 2 GiB) |
| Startup to `/health` 200 | **100.4 s** |

## Phase 2A vs Phase 2B (same host)

Steady-state `dev-smoke` benchmark, requested concurrency 10, server
`max_num_seqs=2` (queueing). Failed requests remain in the denominator.

| Metric | Phase 2A (`mp`) | Phase 2B (`ray`) | Δ vs 2A |
|---|---:|---:|---:|
| Input tok/s | 34.06 | 34.94 | **+2.6%** |
| Output tok/s | 17.13 | 18.26 | **+6.6%** |
| Requests/s | 0.282 | 0.289 | **+2.6%** |
| TTFT p50 (ms) | 14196 | 13557 | **−4.5%** |
| TTFT p95 (ms) | 28486 | 26922 | **−5.5%** |
| E2E p50 (ms) | 21099 | 19988 | **−5.3%** |
| E2E p95 (ms) | 35439 | 33155 | **−6.4%** |
| Error rate | 0 | 0 | 0 |
| GPU memory / rank (MiB used) | 10643 | 10775 | **+1.2%** |
| Startup to healthy (s) | ~189 (2A log timestamps) | 100.4 | **−46.9%** |

These deltas are a same-host executor comparison. They are **not** a claim that
Ray is required to be faster, and they are **not** comparable to Phase 1
(RTX 3090) as a TP speedup.

Raw: gitignored `artifacts/phase2/benchmark_summary.json` (2A) and
`artifacts/phase2/phase2b_benchmark_summary.json` (2B).

## Not claimed

- Multi-node Ray
- Kubernetes / KubeRay
- Prometheus as a stack, KEDA
- Public vLLM or a new public Ray dashboard mapping
- Destroying the rental

## Next

Stop. Wait for explicit approval before any further topology (multi-node,
Kubernetes, metrics stack, KEDA) or before destroying this instance.
