"""Offline PromQL contract for Phase 4A. Does not query a live Prometheus."""

from __future__ import annotations

from typing import Any

import yaml

from inference_platform.paths import repo_root

REQUIRED_SERIES = (
    "vllm:num_requests_running",
    "vllm:num_requests_waiting",
    "vllm:kv_cache_usage_perc",
    "vllm:prompt_tokens_total",
    "vllm:generation_tokens_total",
    "vllm:time_to_first_token_seconds",
    "vllm:e2e_request_latency_seconds",
)


def promql_contract_path():
    return repo_root() / "infra" / "observability" / "promql" / "vllm-acceptance.yaml"


def load_promql_contract() -> dict[str, Any]:
    data = yaml.safe_load(promql_contract_path().read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("PromQL contract must be a mapping")
    return data


def required_series() -> tuple[str, ...]:
    series = load_promql_contract().get("series") or []
    return tuple(str(item) for item in series)


def acceptance_queries() -> dict[str, str]:
    queries = load_promql_contract().get("queries") or {}
    return {str(key): str(value) for key, value in queries.items()}
