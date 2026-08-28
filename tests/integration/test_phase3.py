"""Phase 3 live acceptance. Skipped unless RUN_PHASE3=1 and a ready tunneled endpoint exist.

Reuses the Phase 1 health, model-discovery, metrics, and concurrent SSE contract.
Do not run against a vLLM process that is still loading. Do not apply manifests here.
"""

from __future__ import annotations

import os

import pytest

from inference_platform.config import load_local_env, load_profile
from tests.integration import test_phase1 as phase1

pytestmark = [pytest.mark.integration, pytest.mark.gpu, pytest.mark.timeout(300)]


def _enabled() -> bool:
    return os.environ.get("RUN_PHASE3") == "1"


@pytest.fixture(scope="module")
def phase1_config():
    if not _enabled():
        pytest.skip("Phase 3 live tests require RUN_PHASE3=1 after vLLM is ready")
    load_local_env()
    return load_profile(os.environ.get("INFERENCE_PROFILE", "vast-k3s-replica"))


def test_health_models_metrics(phase1_config) -> None:
    phase1.test_health_models_metrics(phase1_config)


def test_configured_concurrent_streams(phase1_config) -> None:
    phase1.test_configured_concurrent_streams(phase1_config)


def test_loopback_or_explicit_insecure_override(phase1_config) -> None:
    env = phase1_config.env
    host = env.vllm_base_url.split("://", 1)[-1].split("/", 1)[0].split(":")[0]
    loopback = host in {"127.0.0.1", "localhost", "::1"}
    assert loopback or env.allow_insecure_remote_http, (
        "Phase 3 first gate must use SSH-tunneled loopback or correctly configured HTTPS; "
        "refusing public plaintext HTTP"
    )
