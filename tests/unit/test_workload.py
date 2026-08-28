"""Workload prompts and concurrency must match the contract, not silent defaults."""

from __future__ import annotations

import pytest

from inference_client.client import resolve_model_id
from inference_client.prompts import build_prompt, estimate_tokens, workload_token_label
from inference_platform.concurrency import plan_concurrency
from inference_platform.config import load_profile


@pytest.mark.unit
def test_phase1_acceptance_concurrency_comes_from_config() -> None:
    workload = load_profile("authoring").workload
    assert workload.phase1_acceptance_concurrency == 10
    assert 10 in workload.concurrency_levels


@pytest.mark.unit
def test_prompt_meets_configured_token_envelope() -> None:
    spec = build_prompt("Write about {topic}.", "streaming", 128)
    assert spec.estimated_tokens >= 128
    assert spec.meets_envelope
    assert estimate_tokens("Write a short sentence.") < 128
    assert "short-prompt" in workload_token_label(nominal=128, estimated=12, measured=None)
    assert "estimated-prompt-tokens=128" in workload_token_label(
        nominal=128, estimated=128, measured=None
    )


@pytest.mark.unit
def test_concurrency_cap_is_recorded() -> None:
    planned = plan_concurrency(64, cap=32)
    assert planned.requested == 64
    assert planned.effective == 32
    assert planned.capped is True
    uncapped = plan_concurrency(10, cap=None)
    assert uncapped.effective == 10
    assert uncapped.capped is False


@pytest.mark.unit
def test_live_model_prefers_served_alias_then_model_id() -> None:
    assert (
        resolve_model_id(
            ["qwen3.5-9b", "other"],
            served_name="qwen3.5-9b",
            model_id="Qwen/Qwen3.5-9B",
        )
        == "qwen3.5-9b"
    )
    assert (
        resolve_model_id(
            ["Qwen/Qwen3.5-9B"],
            served_name="qwen3.5-9b",
            model_id="Qwen/Qwen3.5-9B",
        )
        == "Qwen/Qwen3.5-9B"
    )
    with pytest.raises(RuntimeError, match="neither"):
        resolve_model_id(["unrelated"], served_name="qwen3.5-9b", model_id="Qwen/Qwen3.5-9B")
