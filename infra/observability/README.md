# Observability (not deployed in Phase 0)

Pinned kube-prometheus-stack chart: 88.6.0.

Later work will verify actual vLLM 0.27.1 metric names before dashboards or KEDA queries. Do not assume names are stable across versions.

Candidate series (to be confirmed against the pinned image):

- `vllm:num_requests_running`
- `vllm:num_requests_waiting`
- `vllm:kv_cache_usage_perc`
- `vllm:prompt_tokens_total`
- `vllm:generation_tokens_total`
- `vllm:time_to_first_token_seconds`
- `vllm:inter_token_latency_seconds`
- `vllm:e2e_request_latency_seconds`

GPU metrics: DCGM Exporter or an explicitly approved equivalent, not claimed yet.
