# Phase 1 gate status

Recorded from the macOS authoring workstation through an SSH tunnel to the
existing Vast vLLM process. Compose was **not** used. No second vLLM process
was started. CUDA/vLLM acceptance for this **single-GPU Vast** path is claimed
only for the checks below. Ray, Kubernetes, Prometheus-as-a-stack, and KEDA
remain **unclaimed**.

## What ran

| Check | Exit status | Notes |
|---|---|---|
| Offline unit tests | 0 | 67 passed |
| SSH tunnel `localhost:8000` → remote `127.0.0.1:18000` | running | Project `.ssh/known_hosts`; StrictHostKeyChecking=yes |
| `GET /health` | 0 | HTTP 200 only |
| `GET /v1/models` | 0 | Live id `Qwen/Qwen3.5-9B` (alias `qwen3.5-9b` was not registered) |
| `GET /metrics` | 0 | HTTP 200, Prometheus text |
| `RUN_PHASE1=1 pytest tests/integration/test_phase1.py -m gpu` | 0 | 2 passed in 14.59s |
| `benchmarks/phase1_load.py --profile vast-single-gpu` | 0 | 90/90 steady-state requests ok |
| Read-only remote discovery | 0 | `nvidia-smi` / `pip show`; no `import torch` |
| Compose `up` / new vLLM | not run | Existing PID 4981 reused |

## Concurrent streams (acceptance)

Ten concurrent SSE chat completions, `phase1_acceptance_concurrency=10`:

- Status `ok`, `saw_done=true`, non-empty output, for all 10
- Live model `Qwen/Qwen3.5-9B`
- TTFT about 0.15–3.5 s (queueing with `max_num_seqs=4`)
- End-to-end about 1.5–5.0 s
- Prompt labels use measured server `usage.prompt_tokens` (109–133 vs nominal 128)

Raw: gitignored `artifacts/phase1/concurrent_streams.json`.

## Benchmark (dev-smoke, existing server)

- Requested concurrency 10, effective concurrency 10, not capped
- Warm-up 30 s (50 requests), measurement 60 s (90 requests)
- Errors 0; failed requests remain in the denominator
- Input ~172 tok/s, output ~90 tok/s, ~1.42 req/s
- TTFT p50 ~2105 ms, p95 ~4217 ms
- E2E p50 ~3989 ms, p95 ~6000 ms
- Metrics scraped before and after
- Aspirational 5000 output tok/s: **not claimed**

Raw: gitignored `artifacts/phase1/benchmark_summary.json` and `benchmark_raw.jsonl`.

## Hardware (read-only discovery)

- GPU: NVIDIA GeForce RTX 3090, 24576 MiB, ~20602 MiB in use after the run
- Driver 580.159.03, reported CUDA 13.0
- vLLM 0.27.1, PyTorch 2.13.0+cu130 (from `pip show`)
- Process PID 4981 still running after tests; `/health` still HTTP 200
- Docker/Compose container inspect: **not applicable** (pre-existing process)

## SSH first contact

Host keys for the rental were stored only in gitignored `.ssh/known_hosts`.
Host-key checking stayed enabled. Fingerprints are not published.

## Deviations

- Phase 1 served the already-loaded 9B override, not a Compose-built replica.
- The process does not expose served alias `qwen3.5-9b`; clients use the live id.
- Requests send `chat_template_kwargs.enable_thinking=false` so smoke output is
  visible without restarting the server with `--reasoning-parser`.
- Authoring-host disk below 5 GiB is WARN, not FAIL (weights live on the GPU host).

Phase 2 (same-host TP / Ray) is not started.
