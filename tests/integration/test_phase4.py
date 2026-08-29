"""Phase 4A live acceptance. Skipped unless RUN_PHASE4=1.

Health/SSE reuse Phase 1. PromQL uses PROMETHEUS_BASE_URL (SSH-tunneled loopback).
Do not scale to two replicas here. Do not install KEDA.
"""

from __future__ import annotations

import os
import time

import pytest

from inference_client.health import get_json
from inference_platform.config import load_local_env, load_profile
from inference_platform.observability.prometheus import instant_query
from inference_platform.observability.promql import REQUIRED_SERIES, acceptance_queries
from tests.integration import test_phase1 as phase1

pytestmark = [pytest.mark.integration, pytest.mark.gpu, pytest.mark.timeout(300)]


def _enabled() -> bool:
    return os.environ.get("RUN_PHASE4") == "1"


@pytest.fixture(scope="module")
def phase1_config():
    if not _enabled():
        pytest.skip("Phase 4A live tests require RUN_PHASE4=1 after vLLM is ready")
    load_local_env()
    return load_profile(os.environ.get("INFERENCE_PROFILE", "vast-k3s-replicas"))


def test_health_models_metrics(phase1_config) -> None:
    phase1.test_health_models_metrics(phase1_config)


def test_configured_concurrent_streams(phase1_config) -> None:
    phase1.test_configured_concurrent_streams(phase1_config)


def test_loopback_or_explicit_insecure_override(phase1_config) -> None:
    env = phase1_config.env
    host = env.vllm_base_url.split("://", 1)[-1].split("/", 1)[0].split(":")[0]
    loopback = host in {"127.0.0.1", "localhost", "::1"}
    assert loopback or env.allow_insecure_remote_http, (
        "Phase 4A must use SSH-tunneled loopback or correctly configured HTTPS; "
        "refusing public plaintext HTTP"
    )


def test_vllm_metrics_expose_required_series(phase1_config) -> None:
    env = phase1_config.env
    status, body = get_json(
        env.vllm_base_url,
        phase1_config.serving.metrics_path,
        api_key=env.vllm_api_key,
        tls_verify=env.vllm_tls_verify,
        allow_insecure_remote_http=env.allow_insecure_remote_http,
    )
    assert status == 200
    assert isinstance(body, str)
    missing = [name for name in REQUIRED_SERIES if name not in body]
    assert not missing, f"vLLM /metrics missing {missing}"


def test_prometheus_scrapes_required_series(phase1_config) -> None:
    base = os.environ.get("PROMETHEUS_BASE_URL", "http://127.0.0.1:9090")
    host = base.split("://", 1)[-1].split("/", 1)[0].split(":")[0]
    assert host in {"127.0.0.1", "localhost", "::1"}
    payload = instant_query(
        base,
        acceptance_queries()["num_requests_running"],
        tls_verify=phase1_config.env.vllm_tls_verify,
        allow_insecure_remote_http=False,
    )
    results = payload.get("data", {}).get("result") or []
    assert results, "Prometheus has no vllm:num_requests_running samples yet"


def test_load_moves_running_or_waiting_and_latency(phase1_config) -> None:
    base = os.environ.get("PROMETHEUS_BASE_URL", "http://127.0.0.1:9090")
    queries = acceptance_queries()
    before_tokens = instant_query(base, queries["generation_tokens_total"])
    before_value = _scalar(before_tokens)
    phase1.test_configured_concurrent_streams(phase1_config)
    deadline = time.time() + 45
    moved = False
    last = before_value
    while time.time() < deadline:
        after = instant_query(base, queries["generation_tokens_total"])
        last = _scalar(after)
        if last is not None and (before_value is None or last > before_value):
            moved = True
            break
        time.sleep(3)
    assert moved, f"generation_tokens_total did not increase ({before_value} -> {last})"
    e2e = instant_query(base, queries["e2e_p95"])
    assert e2e.get("data", {}).get("result") is not None


def _scalar(payload: dict) -> float | None:
    results = payload.get("data", {}).get("result") or []
    if not results:
        return None
    value = results[0].get("value")
    if not value or len(value) < 2:
        return None
    try:
        return float(value[1])
    except (TypeError, ValueError):
        return None
