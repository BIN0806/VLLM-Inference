"""Configuration loading and pin freeze tests."""

from __future__ import annotations

import pytest

from inference_platform.config import load_pins, load_profile


@pytest.mark.unit
def test_authoring_profile_does_not_require_gpu() -> None:
    config = load_profile("authoring")
    assert config.profile.gpu_required is False
    assert config.compute is None
    assert config.model.revision == "3ecffa0ceb27851800f45519bab9c457a04405e1"
    assert config.model.trust_remote_code is False


@pytest.mark.unit
def test_vast_single_gpu_uses_9b_override() -> None:
    config = load_profile("vast-single-gpu")
    assert config.profile.provider == "vast"
    assert config.compute is not None
    assert config.compute.id == "single-gpu"
    assert config.model.model_id == "Qwen/Qwen3.5-9B"
    assert config.model.revision == "c202236235762e1c871ad0ccb60c8ee5ba337b9a"
    assert config.fallback_model is not None
    assert config.fallback_model.model_id == "Qwen/Qwen2.5-1.5B-Instruct-AWQ"
    assert config.tensor_parallel_size == 1


@pytest.mark.unit
def test_env_overrides_model_and_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VLLM_MODEL", "Qwen/Qwen3.5-9B")
    monkeypatch.setenv("VLLM_MAX_MODEL_LEN", "16384")
    monkeypatch.setenv("VLLM_MAX_NUM_SEQS", "4")
    config = load_profile("vast-single-gpu")
    assert config.model_id == "Qwen/Qwen3.5-9B"
    assert config.max_model_len == 16384
    assert config.max_num_seqs == 4


@pytest.mark.unit
def test_pins_are_exact_and_not_latest() -> None:
    pins = load_pins()
    assert pins["vllm"]["version"] == "0.27.1"
    assert pins["vllm"]["official_image"]["tag"] != "latest"
    assert pins["vllm"]["official_image"]["digest_linux_amd64"].startswith("sha256:")
    assert "latest" not in pins["vllm"]["official_image"]["ref"]
    assert pins["models"]["portable_baseline"]["revision"]
    assert pins["models"]["current_validation_override"]["revision"]
    assert pins["charts_and_operators"]["keda"] == "2.20.2"


@pytest.mark.unit
def test_public_dict_omits_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VLLM_API_KEY", "should-not-appear")
    config = load_profile("authoring")
    public = config.public_dict()
    assert "vllm_api_key" not in public
    assert "should-not-appear" not in str(public)


@pytest.mark.unit
def test_open_button_token_fills_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VLLM_API_KEY", raising=False)
    monkeypatch.setenv("OPEN_BUTTON_TOKEN", "vast-open-button-token")
    config = load_profile("authoring")
    assert config.env.vllm_api_key == "vast-open-button-token"
    public = config.public_dict()
    assert "vast-open-button-token" not in str(public)
    assert "open_button_token" not in public


@pytest.mark.unit
def test_vllm_api_key_wins_over_open_button_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VLLM_API_KEY", "explicit-vllm-key")
    monkeypatch.setenv("OPEN_BUTTON_TOKEN", "vast-open-button-token")
    config = load_profile("authoring")
    assert config.env.vllm_api_key == "explicit-vllm-key"
