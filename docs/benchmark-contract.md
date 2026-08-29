# Benchmark contract

Classification: **development smoke, topology acceptance, and baseline
benchmark**, not a production SLO.

The figure “5,000 output tokens per second” is **aspirational**. It is not a Phase 1 acceptance criterion. Do not claim it unless a recorded run demonstrates it. Always report input-token throughput, output-token throughput, and request rate separately.

## Hardware (must be recorded per run)

Fill these from hardware discovery. Do not copy a past rental into a new run.

| Field | How to obtain |
|---|---|
| Provider | `GPU_PROVIDER` |
| Instance id | `GPU_INSTANCE_ID` (rental-specific) |
| GPU model, count, VRAM | `inference-discover-hardware --remote` |
| Driver and reported CUDA | same |
| CPU model/count, host RAM | same |
| Local disk / persistent volume | same |
| OS and container runtime | same |
| Interconnect (PCIe/NVLink) | `nvidia-smi topo -m` when available |
| vLLM, Ray, Python, PyTorch, CUDA runtime | `pip show` / image label, not `import torch` during load |

Example of one past rental (not a default): see `docs/examples/vast-rtx3090-snapshot.example.json`.

## Model and engine (must be recorded per run)

| Field | Portable baseline | Current validation override |
|---|---|---|
| Model ID | `Qwen/Qwen2.5-1.5B-Instruct-AWQ` | `Qwen/Qwen3.5-9B` |
| Revision | `3ecffa0ceb27851800f45519bab9c457a04405e1` | `c202236235762e1c871ad0ccb60c8ee5ba337b9a` |
| License | Apache-2.0 | Apache-2.0 |
| Quantization | AWQ 4-bit | none (BF16) |
| Served alias | `qwen2.5-1.5b-instruct-awq` | `qwen3.5-9b` |
| Official vLLM image | `vllm/vllm-openai:v0.27.1@sha256:c2f3b1b964e47809b722b5e75b61b1e7b39a50f70388cf2bf2418f16a9f31da2` | Overridable via `VLLM_IMAGE` |
| vLLM version | 0.27.1 | 0.27.1 (rental-reported) |

Engine arguments come from serving config plus env overrides: tensor parallel size, pipeline parallel size, executor backend, GPU memory utilization, max model length, max sequences, prefix caching (off by default).

If a fallback model is used, the report must say so. That run cannot pass the originally requested model gate.

## Workload

Source of truth: `configs/workloads/dev-smoke.yaml`. Lengths and concurrency are configuration, not test literals.

Default development envelope:

- Typical prompt: ~128 tokens
- Requested output: 64 tokens
- Concurrency levels: 1, 4, 8, 10
- Phase 1 acceptance: 10 concurrent streaming requests
- Streaming: enabled
- Request timeout: 120 seconds (configurable)
- Warm-up: 30 seconds / 4 requests (excluded from steady-state)
- Measurement window: 60 seconds
- Prefix caching: disabled; prompts do not share a long prefix by default

Optional (not Phase 1 gates):

- Medium: 512 input / 128 output
- Long: 2048 input / 256 output

## Success and metrics

A request succeeds when the health endpoint returns HTTP 200, SSE events are well-formed JSON, generated content is non-empty, a terminal `finish_reason` arrives, the stream ends with `data: [DONE]`, and elapsed time is within the timeout. The OpenAI SDK hides `[DONE]`; acceptance and this benchmark use a raw HTTPX SSE parser.

Concurrency in the report is the **effective** concurrency that ran. If a cap is applied, record both the requested and effective values.

Prompt size is the configured `typical_prompt_tokens` envelope. Construct or pad prompts to that size, or label the run with estimated/measured prompt tokens. Do not report a nominal 128-token workload when the prompt is a short sentence.

Measure at least:

- Input tokens/sec = successful prompt tokens / steady-state seconds
- Output tokens/sec = successful generated tokens / steady-state seconds
- Requests/sec
- p50/p95/p99 TTFT (dispatch → first generated-content chunk)
- p50/p95 inter-token latency when the server exposes it
- p50/p95 end-to-end latency (dispatch → terminal event)
- p95 queue time when available from `/metrics`
- Success and error rate (failed requests stay in the denominator)
- HTTP timeouts
- OOM and restart counts when container/pod inspection is possible
- Peak GPU memory, KV-cache utilization, running and waiting requests

Raw per-request rows are written under `artifacts/phase1/` as JSON/JSONL. Warm-up is stored separately from steady-state.

## Accepted measurements

These results are preserved for interpretation, not as one cross-hardware
leaderboard:

| Gate | Hardware / topology | Output tok/s | Requests/s | TTFT p50/p95 | Interpretation |
|---|---|---:|---:|---:|---|
| Phase 1 | RTX 3090, 9B, TP=1 | ~90 | ~1.42 | ~2.1/4.2 s | Single-GPU streaming baseline |
| Phase 2A | 2× RTX 3060, 9B, TP=2, native `mp` | ~17.13 | ~0.282 | ~14.2/28.5 s | Fit/correctness on constrained GPUs |
| Phase 2B | Same Phase 2 host, TP=2, Ray | ~18.26 | ~0.289 | ~13.6/26.9 s | Controlled same-host executor comparison |
| Phase 4B, one replica | RTX A4000, 1.5B AWQ | ~391 generation tok/s | ~1.03 | Prometheus window only | Capacity baseline |
| Phase 4B, two replicas | 2× RTX A4000, one replica/GPU | ~778 generation tok/s | ~2.03 | Prometheus window only | About 2× aggregate ClusterIP capacity |

The Phase 4B rows use Prometheus server counters over matched loaded windows,
not the Phase 1/2 client benchmark schema. The in-cluster load-generator logs
were deleted, so the load-distribution addendum does not claim a measured
client error rate.

## Gate correctness versus performance

A phase passes on its stated correctness, streaming, reliability, topology,
and reproducibility criteria. It does not fail merely because throughput is
below 5,000 output tokens/s. The finished project still does not claim that
target.

See [Final project status](project-status.md) for the complete evidence and
cross-phase boundaries.
