# Phase 1 gate status

Recorded from the macOS authoring workstation. Compose was **not** used. No
second vLLM process was started by this repo. CUDA/vLLM acceptance for this
**single-GPU Vast** path is claimed only for the checks below. Ray, Kubernetes,
Prometheus-as-a-stack, and KEDA remain **unclaimed**.

SSH-tunneled tests hit vLLM on remote `127.0.0.1:18000` and **skip** Vast Caddy.
A later one-time public mapped-port request used
`Authorization: Bearer ${OPEN_BUTTON_TOKEN}` over **plaintext HTTP**. That was
authentication-mechanics validation only: Caddy returned 401 without a token
and 200 with a token. It does **not** prove secure external transport. Bearer
auth without TLS provides no confidentiality; an on-path observer could read
the token and the prompt. Treat that instance token as **potentially exposed**.
Destroying the temporary Vast instance retires it. The request was not
repeated. Hosts, tokens, and fingerprints are not published.

The HTTP client now refuses to send `VLLM_API_KEY` or `OPEN_BUTTON_TOKEN` to a
non-loopback `http://` URL unless `ALLOW_INSECURE_REMOTE_HTTP=true` (lab-only,
default false). Loopback SSH tunnels may keep using HTTP. Future testing must
use an SSH tunnel or properly configured HTTPS.

## What ran

| Check | Exit status | Notes |
|---|---|---|
| Offline unit tests | 0 | 78 passed |
| SSH tunnel `localhost:8000` → remote `127.0.0.1:18000` | 0 | Used for SSE/benchmark; now closed |
| `GET /health` (tunnel) | 0 | HTTP 200 only |
| `GET /v1/models` (tunnel) | 0 | Live id `Qwen/Qwen3.5-9B` (alias `qwen3.5-9b` was not registered) |
| `GET /metrics` (tunnel) | 0 | HTTP 200, Prometheus text |
| `RUN_PHASE1=1 pytest tests/integration/test_phase1.py -m gpu` | 0 | 2 passed in 14.59s |
| `benchmarks/phase1_load.py --profile vast-single-gpu` | 0 | 90/90 steady-state requests ok |
| Public Caddy `GET /v1/models` without Bearer | 0 | HTTP **401** — lab auth-mechanics check only |
| Public Caddy Bearer over plaintext HTTP | 0 | One-time diagnostic: `/v1/models`, `/v1/chat/completions`, `/metrics` returned **200**. **Not** secure transport. Token treated as exposed. Not repeated. |
| Direct TLS to the vLLM mapped port | failed | `WRONG_VERSION_NUMBER` — Caddy on the vLLM mapping is HTTP (`ENABLE_HTTPS` unset) |
| Cloudflare quick tunnel HTTPS for vLLM | unavailable | trycloudflare 429/500; no public HTTPS URL |
| Read-only remote discovery | 0 | `nvidia-smi` / `pip show`; no `import torch` |
| Compose `up` / new vLLM | not run | Existing Vast-supervised process reused |
| SSH tunnel after the Caddy probe | closed | No local `ssh -L`; `localhost:8000` not listening |

## Concurrent streams (acceptance)

Ten concurrent SSE chat completions through the SSH tunnel,
`phase1_acceptance_concurrency=10`:

- Status `ok`, `saw_done=true`, non-empty output, for all 10
- Live model `Qwen/Qwen3.5-9B`
- TTFT about 0.15–3.5 s (queueing with `max_num_seqs=4` on that process)
- End-to-end about 1.5–5.0 s
- Prompt labels use measured server `usage.prompt_tokens` (109–133 vs nominal 128)

Raw: gitignored `artifacts/phase1/concurrent_streams.json`.

## Benchmark (dev-smoke, tunneled existing server)

- Requested concurrency 10, effective concurrency 10, not capped
- Warm-up 30 s (50 requests), measurement 60 s (90 requests)
- Errors 0; failed requests remain in the denominator
- Input ~172 tok/s, output ~90 tok/s, ~1.42 req/s
- TTFT p50 ~2105 ms, p95 ~4217 ms
- E2E p50 ~3989 ms, p95 ~6000 ms
- Metrics scraped before and after
- Aspirational 5000 output tok/s: **not claimed**

Raw: gitignored `artifacts/phase1/benchmark_summary.json` and `benchmark_raw.jsonl`.

## Vast Caddy (one-time lab authentication-mechanics check)

This was **not** a secure production exposure. The Open-button proxy listens on
container port 8000 and reverse-proxies to remote `127.0.0.1:18000`. Auth
matchers: Bearer token, `?token=`, auth cookie, or HTTP basic. Unauthenticated
`/v1/models` returned 401. Authenticated `/v1/models`, `/v1/chat/completions`,
and `/metrics` returned 200.

Those authenticated calls used the public mapped port over **plaintext HTTP**.
`ENABLE_HTTPS` was unset; Cloudflare quick tunnels were unavailable (429/500).
TLS to the mapped vLLM port failed (`WRONG_VERSION_NUMBER`). Bearer
authentication without TLS does not protect token or prompt confidentiality.
The instance token is treated as potentially exposed and is retired when the
temporary Vast rental is destroyed.

Do not repeat a public plaintext-authenticated request. Further tests must use
an SSH tunnel to loopback or HTTPS with a verified certificate. The client
refuses credentials on non-loopback `http://` URLs unless
`ALLOW_INSECURE_REMOTE_HTTP=true`.

Raw scrape: gitignored `artifacts/phase1/metrics_https.prom`.

## `/metrics` names (vLLM 0.27.1, exact scrape)

115 names. Histogram/summary families appear as `_bucket` / `_count` / `_sum` /
`_created` where the process exported them. `http_request_duration_highr_seconds_bucket`
had no matching `_count`/`_sum` in this snapshot.

### Process / HTTP

- `http_request_duration_highr_seconds_bucket`
- `http_request_size_bytes_count`
- `http_request_size_bytes_created`
- `http_request_size_bytes_sum`
- `http_requests_created`
- `http_requests_total`
- `http_response_size_bytes_count`
- `http_response_size_bytes_created`
- `http_response_size_bytes_sum`
- `process_cpu_seconds_total`
- `process_max_fds`
- `process_open_fds`
- `process_resident_memory_bytes`
- `process_start_time_seconds`
- `process_virtual_memory_bytes`
- `python_gc_collections_total`
- `python_gc_objects_collected_total`
- `python_gc_objects_uncollectable_total`
- `python_info`

### `vllm:`

- `vllm:cache_config_info`
- `vllm:e2e_request_latency_seconds_bucket`
- `vllm:e2e_request_latency_seconds_count`
- `vllm:e2e_request_latency_seconds_created`
- `vllm:e2e_request_latency_seconds_sum`
- `vllm:engine_sleep_state`
- `vllm:estimated_flops_per_gpu_created`
- `vllm:estimated_flops_per_gpu_total`
- `vllm:estimated_read_bytes_per_gpu_created`
- `vllm:estimated_read_bytes_per_gpu_total`
- `vllm:estimated_write_bytes_per_gpu_created`
- `vllm:estimated_write_bytes_per_gpu_total`
- `vllm:external_prefix_cache_hits_created`
- `vllm:external_prefix_cache_hits_total`
- `vllm:external_prefix_cache_queries_created`
- `vllm:external_prefix_cache_queries_total`
- `vllm:generation_tokens_created`
- `vllm:generation_tokens_total`
- `vllm:inter_token_latency_seconds_bucket`
- `vllm:inter_token_latency_seconds_count`
- `vllm:inter_token_latency_seconds_created`
- `vllm:inter_token_latency_seconds_sum`
- `vllm:iteration_tokens_total_bucket`
- `vllm:iteration_tokens_total_count`
- `vllm:iteration_tokens_total_created`
- `vllm:iteration_tokens_total_sum`
- `vllm:kv_cache_usage_perc`
- `vllm:mm_cache_hits_created`
- `vllm:mm_cache_hits_total`
- `vllm:mm_cache_queries_created`
- `vllm:mm_cache_queries_total`
- `vllm:num_preemptions_created`
- `vllm:num_preemptions_total`
- `vllm:num_requests_running`
- `vllm:num_requests_waiting`
- `vllm:num_requests_waiting_by_reason`
- `vllm:prefix_cache_hits_created`
- `vllm:prefix_cache_hits_total`
- `vllm:prefix_cache_queries_created`
- `vllm:prefix_cache_queries_total`
- `vllm:prompt_tokens_by_source_created`
- `vllm:prompt_tokens_by_source_total`
- `vllm:prompt_tokens_cached_created`
- `vllm:prompt_tokens_cached_total`
- `vllm:prompt_tokens_created`
- `vllm:prompt_tokens_total`
- `vllm:request_decode_time_seconds_bucket`
- `vllm:request_decode_time_seconds_count`
- `vllm:request_decode_time_seconds_created`
- `vllm:request_decode_time_seconds_sum`
- `vllm:request_generation_tokens_bucket`
- `vllm:request_generation_tokens_count`
- `vllm:request_generation_tokens_created`
- `vllm:request_generation_tokens_sum`
- `vllm:request_inference_time_seconds_bucket`
- `vllm:request_inference_time_seconds_count`
- `vllm:request_inference_time_seconds_created`
- `vllm:request_inference_time_seconds_sum`
- `vllm:request_max_num_generation_tokens_bucket`
- `vllm:request_max_num_generation_tokens_count`
- `vllm:request_max_num_generation_tokens_created`
- `vllm:request_max_num_generation_tokens_sum`
- `vllm:request_params_max_tokens_bucket`
- `vllm:request_params_max_tokens_count`
- `vllm:request_params_max_tokens_created`
- `vllm:request_params_max_tokens_sum`
- `vllm:request_params_n_bucket`
- `vllm:request_params_n_count`
- `vllm:request_params_n_created`
- `vllm:request_params_n_sum`
- `vllm:request_prefill_kv_computed_tokens_bucket`
- `vllm:request_prefill_kv_computed_tokens_count`
- `vllm:request_prefill_kv_computed_tokens_created`
- `vllm:request_prefill_kv_computed_tokens_sum`
- `vllm:request_prefill_time_seconds_bucket`
- `vllm:request_prefill_time_seconds_count`
- `vllm:request_prefill_time_seconds_created`
- `vllm:request_prefill_time_seconds_sum`
- `vllm:request_prompt_tokens_bucket`
- `vllm:request_prompt_tokens_count`
- `vllm:request_prompt_tokens_created`
- `vllm:request_prompt_tokens_sum`
- `vllm:request_queue_time_seconds_bucket`
- `vllm:request_queue_time_seconds_count`
- `vllm:request_queue_time_seconds_created`
- `vllm:request_queue_time_seconds_sum`
- `vllm:request_success_created`
- `vllm:request_success_total`
- `vllm:request_time_per_output_token_seconds_bucket`
- `vllm:request_time_per_output_token_seconds_count`
- `vllm:request_time_per_output_token_seconds_created`
- `vllm:request_time_per_output_token_seconds_sum`
- `vllm:time_to_first_token_seconds_bucket`
- `vllm:time_to_first_token_seconds_count`
- `vllm:time_to_first_token_seconds_created`
- `vllm:time_to_first_token_seconds_sum`

Do not assume these names for KEDA or dashboards until an observability phase
scrapes them from a pinned Prometheus stack.

## Hardware (read-only discovery)

- GPU: NVIDIA GeForce RTX 3090, 24576 MiB, ~20602 MiB in use after the tunnel run
- Driver 580.159.03, reported CUDA 13.0
- vLLM 0.27.1, PyTorch 2.13.0+cu130 (from `pip show`)
- Tunnel-run process PID 4981 was healthy after those tests
- The Caddy probe waited ~184 s for `/health` HTTP 200 on a later
  supervisor-managed `vllm serve` of the same model (this repo did not start it)
- Docker/Compose container inspect: **not applicable** (pre-existing process)

## SSH first contact and tunnel close

Host keys for the rental were stored only in gitignored `.ssh/known_hosts`.
Host-key checking stayed enabled. Fingerprints are not published.

The Phase 1 SSH tunnel was closed: no local `ssh -L` / `open_vllm_tunnel`
process, and nothing listening on authoring `localhost:8000`.

## Deviations

- Phase 1 served the already-loaded 9B override, not a Compose-built replica.
- The process does not expose served alias `qwen3.5-9b`; clients use the live id.
- Requests send `chat_template_kwargs.enable_thinking=false` so smoke output is
  visible without restarting the server with `--reasoning-parser`.
- Authoring-host disk below 5 GiB is WARN, not FAIL (weights live on the GPU host).
- Public vLLM mapping was HTTP+Caddy auth (`ENABLE_HTTPS` unset; Cloudflare
  quick tunnels unavailable). TLS was not claimed. The plaintext Bearer call is
  a one-time lab diagnostic; the token is treated as exposed.
- Destroying the temporary Vast instance retires that instance-specific token.
- Phase 2, if approved later, must use an SSH tunnel unless HTTPS is configured.

Phase 2 (same-host TP / Ray) is not started.
