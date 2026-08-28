"""Phase 1 integration tests. Skipped unless RUN_PHASE1=1 and a live endpoint exist.

Do not run this module against a vLLM process that is still loading.
Acceptance uses the raw SSE transport, including the `data: [DONE]` marker.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

import pytest

from inference_client.client import build_client, list_models
from inference_client.health import get_json
from inference_client.prompts import build_prompt, workload_token_label
from inference_client.sse import stream_chat_completion_sse
from inference_platform.config import load_local_env, load_profile
from inference_platform.paths import artifacts_dir
from inference_platform.wait import wait_for_service

pytestmark = [pytest.mark.integration, pytest.mark.gpu]


def _enabled() -> bool:
    return os.environ.get("RUN_PHASE1") == "1"


@pytest.fixture(scope="module")
def phase1_config():
    if not _enabled():
        pytest.skip("Phase 1 live tests require RUN_PHASE1=1 after vLLM is ready")
    load_local_env()
    return load_profile(os.environ.get("INFERENCE_PROFILE", "vast-single-gpu"))


def test_health_models_metrics(phase1_config) -> None:
    env = phase1_config.env
    wait_for_service(
        env.vllm_base_url,
        timeout_seconds=30,
        api_key=env.vllm_api_key,
        tls_verify=env.vllm_tls_verify,
        health_path=phase1_config.serving.health_path,
    )
    health_status, _ = get_json(
        env.vllm_base_url,
        phase1_config.serving.health_path,
        api_key=env.vllm_api_key,
        tls_verify=env.vllm_tls_verify,
    )
    assert health_status == 200
    client = build_client(env.vllm_base_url, env.vllm_api_key, tls_verify=env.vllm_tls_verify)
    models = list_models(client)
    assert phase1_config.served_name in models or phase1_config.model_id in models
    metrics_status, body = get_json(
        env.vllm_base_url,
        phase1_config.serving.metrics_path,
        api_key=env.vllm_api_key,
        tls_verify=env.vllm_tls_verify,
    )
    assert metrics_status == 200
    assert isinstance(body, str)
    assert len(body) > 0


def test_configured_concurrent_streams(phase1_config) -> None:
    env = phase1_config.env
    workload = phase1_config.workload
    concurrency = workload.phase1_acceptance_concurrency
    template = workload.prompt_template or "Write one sentence about {topic}."
    topics = workload.topics or ["inference"]
    specs = [
        build_prompt(template, topics[i % len(topics)], workload.typical_prompt_tokens)
        for i in range(concurrency)
    ]
    results = []

    def _one(spec):
        result = stream_chat_completion_sse(
            base_url=env.vllm_base_url,
            model=phase1_config.served_name,
            messages=[{"role": "user", "content": spec.text}],
            max_tokens=workload.requested_output_tokens,
            api_key=env.vllm_api_key,
            timeout=workload.request_timeout_seconds,
            tls_verify=env.vllm_tls_verify,
        )
        return spec, result

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(_one, spec) for spec in specs]
        for future in as_completed(futures):
            results.append(future.result())

    failures = [
        result
        for _spec, result in results
        if result.status != "ok"
        or not result.terminal
        or not result.saw_done
        or not result.output_text
    ]
    report_dir = artifacts_dir() / "phase1"
    report_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "profile": phase1_config.profile.id,
        "model_id": phase1_config.model_id,
        "revision": phase1_config.revision,
        "served_model_name": phase1_config.served_name,
        "fallback_used": False,
        "requested_concurrency": concurrency,
        "effective_concurrency": concurrency,
        "requests": [
            {
                "status": result.status,
                "ttft_ms": result.ttft_ms,
                "e2e_ms": result.e2e_ms,
                "output_chars": len(result.output_text),
                "terminal": result.terminal,
                "saw_done": result.saw_done,
                "finish_reason": result.finish_reason,
                "error": result.error,
                "estimated_prompt_tokens": spec.estimated_tokens,
                "measured_prompt_tokens": (result.usage or {}).get("prompt_tokens"),
                "token_label": workload_token_label(
                    nominal=workload.typical_prompt_tokens,
                    estimated=spec.estimated_tokens,
                    measured=(result.usage or {}).get("prompt_tokens"),
                ),
            }
            for spec, result in results
        ],
    }
    (report_dir / "concurrent_streams.json").write_text(json.dumps(payload, indent=2) + "\n")
    assert not failures, f"{len(failures)} stream(s) failed"
    assert all(spec.meets_envelope for spec, _result in results)
