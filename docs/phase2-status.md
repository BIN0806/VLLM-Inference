# Phase 2A gate status

Recorded from the macOS authoring workstation. CUDA/vLLM ran on one two-GPU
Vast rental over SSH. Compose, Kubernetes, KEDA, and Phase 2B Ray serving were
**not** used. Multi-node Ray is **not** claimed.

SSH-tunneled tests hit vLLM on remote loopback only. No public endpoint was
opened. No Bearer token was sent over public plaintext HTTP. Hosts, ports,
fingerprints, and tokens are not published.

Phase 1 used a **single RTX 3090**. Phase 2A uses **two RTX 3060 12 GiB**
cards. Throughput here is **not** an apples-to-apples tensor-parallel speedup
comparison.

## Gate decision: **GO for Phase 2A**. **STOP before Phase 2B.**

Native same-host TP=2 with executor backend `mp` is serving the pinned 9B
model. Request approval before starting Phase 2B (same-host Ray only).

## Authorization that was followed

- Stopped only the Vast template Supervisor program `vllm`.
- Started a native Phase 2A `vllm serve` bound to remote `127.0.0.1:18000`.
- Did not delete `/workspace/models`, clear caches, destroy/restart the
  instance, begin Phase 2B, or expose a public endpoint.
- Access remained SSH-tunneled loopback only.

## Before stop (sanitized evidence)

Supervisor program name: `vllm` (`/etc/supervisor/conf.d/vllm.conf`,
`command=/opt/supervisor-scripts/vllm.sh`). At evidence capture the template
process had already **EXITED** after KV-cache OOM (`max_model_len=32000`,
`max_num_seqs=8`, `gpu_memory_utilization≈0.92`, `enforce_eager=False`).
Port 18000 was free. Both GPUs were ~1 MiB used.

Pinned snapshot complete: `Qwen/Qwen3.5-9B` revision
`c202236235762e1c871ad0ccb60c8ee5ba337b9a`, four of four shards (~18 GiB).
Disk free was 5.39 GiB: **NO-GO** for another download or image build;
**conditional GO** to reuse the existing snapshot.

## Stop procedure

1. Resolved Supervisor name `vllm`.
2. Set `autostart=false` in `vllm.conf` and ran `supervisorctl stop vllm`.
3. Status: `vllm STOPPED Not started`.
4. No API server / EngineCore / workers from the template remained.
5. Port 18000 was free, then later bound only by the Phase 2A process.
6. GPUs returned to ~1 MiB, then rose after Phase 2A load.
7. `/workspace/models` was not deleted.

Ray GCS from the Vast template is still running on this **one** host. Phase 2A
does not use Ray actors. That leftover is not multi-node Ray and was not
turned into Phase 2B serving.

## Startup failures (preserved) and recorded fallbacks

The 9B model was **not** switched. The 1.5B fallback was **not** used.
`NCCL_P2P_DISABLE=1` was **not** required.

1. First starts inherited host `HF_HOME` (`/workspace/.hf_home`), which holds
   tokenizer/config only. Weights live under `/workspace/models`. Workers
   failed with `Cannot find any model weights`. Fix: symlink already-local
   tokenizer/config into the weight snapshot (no download, no shard copies)
   and serve that local snapshot with `HF_HUB_OFFLINE=1` and
   `HF_HUB_DISABLE_XET=1`. Served name remained `Qwen/Qwen3.5-9B`.
2. With weights loaded, VL encoder profiling reserved a 16384-token encoder
   cache. Available KV was 0.03 GiB vs 0.15 GiB needed for 8192 (engine
   estimated max length 528). Authorized 8192/2 and 4096/1 both failed for
   this reason, including an `NCCL_P2P_DISABLE=1` retry that was unnecessary
   for NCCL (NCCL had already initialized).
3. Recorded compatibility fallback that **did** work, still on 8192 / 2 seqs /
   `gpu_memory_utilization=0.90` / `--enforce-eager`:
   `--skip-mm-profiling` and `--limit-mm-per-prompt {"image":0,"video":0}`.
   This is text-only serving of the same 9B checkpoint. Custom allreduce was
   already disabled because the platform lacks GPU P2P.

After that fallback: model load **8.46 GiB**/rank, available KV **1.62 GiB**.

## Live Phase 2A configuration

| Setting | Value |
|---|---|
| Model | `Qwen/Qwen3.5-9B` (live `/v1/models` id) |
| Revision | `c202236235762e1c871ad0ccb60c8ee5ba337b9a` |
| Tensor parallel | 2 |
| Pipeline parallel | 1 |
| Executor | `mp` (`multiproc_executor`, `world_size=2`) |
| Max model length | 8192 |
| Max sequences | 2 |
| GPU memory utilization | 0.90 |
| Eager | `--enforce-eager` |
| CUDA devices | 0 and 1 |
| Bind | remote `127.0.0.1:18000` only |
| Offline | `HF_HUB_OFFLINE=1`, `HF_HUB_DISABLE_XET=1` |
| Disk after start | 5.22 GiB free (fail threshold 2 GiB) |

## Acceptance

| Check | Result |
|---|---|
| `GET /health` | HTTP **200** |
| `GET /v1/models` | live id `Qwen/Qwen3.5-9B` (`max_model_len` 8192) |
| GPU allocations | 10633 MiB used on **both** RTX 3060s (12288 MiB total) |
| Logs | `world_size=2`, `multiproc_executor`, `Worker_TP0` / `Worker_TP1`; no Ray actors for the engine |
| Ten concurrent SSE | 10/10 `ok`, non-empty output, `data: [DONE]` |
| Metrics | tunneled `/metrics` HTTP 200 (Prometheus text) |
| Benchmark | `benchmarks/phase1_load.py --profile vast-two-gpu` |

## Concurrent streams (acceptance)

Ten concurrent SSE chat completions through the SSH tunnel,
`phase1_acceptance_concurrency=10`, server `max_num_seqs=2` (queueing):

- Status `ok`, `saw_done=true`, non-empty output, for all 10
- Live model `Qwen/Qwen3.5-9B`
- TTFT about 0.24–31.4 s (queueing)
- End-to-end about 10.9–38.1 s
- Prompt labels use measured server `usage.prompt_tokens`

Raw: gitignored `artifacts/phase2/concurrent_streams.json`.

Integration: `RUN_PHASE1=1 INFERENCE_PROFILE=vast-two-gpu pytest tests/integration/test_phase1.py -m gpu` — 2 passed in 47.14 s.

## Benchmark (dev-smoke, tunneled Phase 2A server)

- Requested concurrency 10, effective concurrency 10, not capped
- Warm-up 30 s (10 requests), measurement 60 s (20 requests)
- Errors 0; failed requests remain in the denominator
- Input ~34 tok/s, output ~17 tok/s, ~0.28 req/s
- TTFT p50 ~14.2 s, p95 ~28.5 s
- E2E p50 ~21.1 s, p95 ~35.4 s
- Metrics scraped before and after
- GPU model: 2 × NVIDIA GeForce RTX 3060 12 GiB
- Topology: GPU0↔GPU1 **SYS** (cross-NUMA); **no P2P**
- Fallback status: same 9B model; skip-mm-profiling + `limit-mm-per-prompt`
  image=0,video=0; `NCCL_P2P_DISABLE` not set; 8192 / 2 seqs / 0.90 / eager
- Aspirational 5000 output tok/s: **not claimed**
- **Not** comparable to Phase 1 RTX 3090 single-GPU throughput as a TP speedup

Raw: gitignored `artifacts/phase2/benchmark_summary.json` and `benchmark_raw.jsonl`.

## Hardware (this rental)

- 2 × NVIDIA GeForce RTX 3060, 12288 MiB each
- Driver 580.126.09, reported CUDA 13.0
- vLLM 0.27.1, PyTorch 2.13.0+cu130
- PCIe: GPU0↔GPU1 SYS, GPUs on NUMA 0 and 1, no P2P
- `/dev/shm` 23.0 GiB
- Disk: 24.0 GiB allocated; ~5.2 GiB free after start

## GitHub Actions

The previous `phase-2` workflow completed in **0 seconds with no jobs**
(malformed YAML). Replacement on this branch:

- `on: push`, `pull_request`, `workflow_dispatch`
- Python 3.12 on `ubuntu-24.04`
- `uv sync --frozen --python 3.12 --extra dev`
- Ruff format, Ruff lint, `pytest tests/unit -m unit`
- Pinned `actions/checkout` and `astral-sh/setup-uv` by commit SHA
- No secrets, no GPU job

Successful push run: 13 s, job **Python 3.12 lint and unit tests**
(`https://github.com/BIN0806/VLLM-Inference/actions/runs/33195294633`).
CI is independent of this live GPU gate.

## Not claimed

- Phase 2B / Ray executor / Ray Serve
- Multi-node Ray
- Public HTTPS or a mapped external vLLM port
- Compose `up`, Kubernetes, Prometheus-as-a-stack, KEDA
- Apples-to-apples TP speedup vs Phase 1

## Next

Phase 2A is complete. **Do not start Phase 2B until explicitly approved.**
Phase 2B, if approved, is same-host Ray only on this rental. Do not claim
multi-node. Keep SSH-tunneled loopback access. Do not delete the model cache
or destroy the instance unless asked.
