"""Unit tests for secret redaction."""

from __future__ import annotations

import os

import pytest

from inference_platform.secrets import redact_mapping, redact_text


@pytest.mark.unit
def test_redact_env_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VLLM_API_KEY", "super-secret-token-value")
    assert "super-secret-token-value" not in redact_text("header super-secret-token-value")
    assert "***REDACTED***" in redact_text("header super-secret-token-value")


@pytest.mark.unit
def test_redact_mapping_by_key() -> None:
    payload = {"vllm_api_key": "abc12345", "model": "Qwen/Qwen3.5-9B"}
    redacted = redact_mapping(payload)
    assert redacted["vllm_api_key"] == "***REDACTED***"
    assert redacted["model"] == "Qwen/Qwen3.5-9B"


@pytest.mark.unit
def test_does_not_require_secret_present() -> None:
    os.environ.pop("HF_TOKEN", None)
    assert redact_text("no secrets here") == "no secrets here"
