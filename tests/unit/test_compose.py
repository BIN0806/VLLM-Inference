"""Compose interpolation uses an env file, not service env_file, and must match the profile."""

from __future__ import annotations

from pathlib import Path

import pytest

from inference_platform.compose import (
    ComposeProfileMismatch,
    interpolate,
    merge_compose_env,
    render_vllm_service,
    validate_rendered_service,
)
from inference_platform.config import load_profile
from inference_platform.paths import repo_root

_COMPOSE_ENV_KEYS = (
    "VLLM_MODEL",
    "MODEL_PATH",
    "MODEL_REVISION",
    "SERVED_MODEL_NAME",
    "VLLM_TENSOR_PARALLEL_SIZE",
    "VLLM_PIPELINE_PARALLEL_SIZE",
    "VLLM_MAX_MODEL_LEN",
    "VLLM_MAX_NUM_SEQS",
    "VLLM_GPU_MEMORY_UTILIZATION",
    "DISTRIBUTED_EXECUTOR_BACKEND",
    "HOST_BIND",
    "HOST_PORT",
    "CONTAINER_PORT",
    "VLLM_API_KEY",
    "MODEL_CONFIG",
    "COMPUTE_PROFILE",
)


@pytest.fixture
def isolated_compose_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _COMPOSE_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _env(**overrides: str) -> dict[str, str]:
    base = {
        "HOST_BIND": "127.0.0.1",
        "HOST_PORT": "8000",
        "CONTAINER_PORT": "8000",
        "VLLM_MODEL": "Qwen/Qwen3.5-9B",
        "MODEL_REVISION": "c202236235762e1c871ad0ccb60c8ee5ba337b9a",
        "SERVED_MODEL_NAME": "qwen3.5-9b",
        "VLLM_TENSOR_PARALLEL_SIZE": "1",
        "VLLM_MAX_MODEL_LEN": "16384",
        "VLLM_API_KEY": "test-key-alpha",
    }
    base.update(overrides)
    return base


@pytest.mark.unit
def test_nested_interpolation() -> None:
    value = "${MODEL_PATH:-${VLLM_MODEL:-fallback-model}}"
    assert interpolate(value, {"VLLM_MODEL": "from-env"}) == "from-env"
    assert interpolate(value, {"MODEL_PATH": "explicit"}) == "explicit"
    assert interpolate(value, {}) == "fallback-model"


@pytest.mark.unit
def test_render_changes_with_model_revision_context_tp_and_api_key() -> None:
    first = render_vllm_service(_env())
    second = render_vllm_service(
        _env(
            VLLM_MODEL="Qwen/Qwen2.5-1.5B-Instruct-AWQ",
            MODEL_REVISION="3ecffa0ceb27851800f45519bab9c457a04405e1",
            VLLM_MAX_MODEL_LEN="2048",
            VLLM_TENSOR_PARALLEL_SIZE="2",
            VLLM_API_KEY="test-key-beta",
        )
    )
    assert first["model"] != second["model"]
    assert first["revision"] != second["revision"]
    assert first["max_model_len"] != second["max_model_len"]
    assert first["tensor_parallel_size"] != second["tensor_parallel_size"]
    assert first["api_key"] != second["api_key"]
    assert first["api_key"] == "test-key-alpha"
    assert second["api_key"] == "test-key-beta"


@pytest.mark.unit
def test_default_publish_bind_is_localhost_and_no_container_name() -> None:
    rendered = render_vllm_service(_env())
    assert rendered["container_name"] is None
    assert any(str(port).startswith("127.0.0.1:") for port in rendered["ports"])


@pytest.mark.unit
def test_profile_fills_compose_when_env_omits_model(isolated_compose_env: None) -> None:
    config = load_profile("vast-single-gpu")
    merged = merge_compose_env(config, {"HOST_BIND": "127.0.0.1"})
    rendered = render_vllm_service(merged)
    validate_rendered_service(config, rendered)
    assert rendered["model"] == config.model_id
    assert rendered["revision"] == config.revision


@pytest.mark.unit
def test_profile_and_env_model_disagreement_is_hard_error(isolated_compose_env: None) -> None:
    config = load_profile("vast-single-gpu")
    with pytest.raises(ComposeProfileMismatch, match="VLLM_MODEL"):
        merge_compose_env(config, {"VLLM_MODEL": "Qwen/Qwen2.5-1.5B-Instruct-AWQ"})


@pytest.mark.unit
def test_missing_env_file_is_a_cli_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from inference_platform.compose import main

    missing = tmp_path / "no.env"
    code = main(["check", "--profile", "authoring", "--env-file", str(missing)])
    assert code == 1
    assert "missing" in capsys.readouterr().err.lower()


@pytest.mark.unit
def test_makefile_passes_compose_env_file_for_interpolation() -> None:
    text = (repo_root() / "Makefile").read_text(encoding="utf-8")
    assert "COMPOSE_ENV_FILE ?= .env.local" in text
    assert "--env-file $(COMPOSE_EXPORT)" in text
    assert "compose-env-check" in text
    assert "Compose interpolation does not read service env_file" in text
    compose = (repo_root() / "docker" / "compose.yaml").read_text(encoding="utf-8")
    assert "container_name" not in compose
    assert "127.0.0.1" in compose
