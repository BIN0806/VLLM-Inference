"""Topology validation: fail-fast, never assume TP or replica meaning."""

from __future__ import annotations

import pytest

from inference_platform.config import load_profile
from inference_platform.fallback import maybe_model_fallback, maybe_tp_fallback
from inference_platform.topology import GpuDevice, HardwareSnapshot, validate_topology


@pytest.fixture(autouse=True)
def _isolate_topology_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "COMPUTE_PROFILE",
        "MODEL_CONFIG",
        "INFERENCE_PROFILE",
        "VLLM_MODEL",
        "VLLM_TENSOR_PARALLEL_SIZE",
        "VLLM_PIPELINE_PARALLEL_SIZE",
        "DISTRIBUTED_EXECUTOR_BACKEND",
        "ALLOW_MODEL_FALLBACK",
        "ALLOW_TP_FALLBACK",
    ):
        monkeypatch.delenv(name, raising=False)


def _one_gpu(vram_mib: int = 24576) -> HardwareSnapshot:
    return HardwareSnapshot(
        gpu_count=1,
        gpus=[GpuDevice(index=0, name="NVIDIA GeForce RTX 3090", vram_mib=vram_mib)],
        source="test",
    )


@pytest.mark.unit
def test_tp_two_fails_on_one_gpu(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VLLM_TENSOR_PARALLEL_SIZE", "2")
    config = load_profile("vast-single-gpu")
    report = validate_topology(config, _one_gpu())
    assert not report.ok
    assert any(issue.code == "tp-exceeds-gpus" for issue in report.issues)


@pytest.mark.unit
def test_single_gpu_profile_rejects_tp_override_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VLLM_TENSOR_PARALLEL_SIZE", "2")
    config = load_profile("vast-single-gpu")
    report = validate_topology(config, _one_gpu())
    assert any(issue.code in {"tp-exceeds-gpus", "single-gpu-tp"} for issue in report.issues)


@pytest.mark.unit
def test_model_that_cannot_fit_fails() -> None:
    config = load_profile("vast-single-gpu")
    tiny = HardwareSnapshot(
        gpu_count=1,
        gpus=[GpuDevice(index=0, name="NVIDIA GeForce GTX 1060", vram_mib=6144)],
        source="test",
    )
    report = validate_topology(config, tiny)
    assert not report.ok
    assert any(issue.code == "model-does-not-fit" for issue in report.issues)


@pytest.mark.unit
def test_silent_tp_fallback_is_forbidden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VLLM_TENSOR_PARALLEL_SIZE", "2")
    monkeypatch.setenv("ALLOW_TP_FALLBACK", "false")
    config = load_profile("vast-single-gpu")
    report = validate_topology(config, _one_gpu())
    tp, event = maybe_tp_fallback(config, report)
    assert tp == 2
    assert event is None


@pytest.mark.unit
def test_explicit_tp_fallback_is_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VLLM_TENSOR_PARALLEL_SIZE", "2")
    monkeypatch.setenv("ALLOW_TP_FALLBACK", "true")
    config = load_profile("vast-single-gpu")
    report = validate_topology(config, _one_gpu())
    tp, event = maybe_tp_fallback(config, report)
    assert event is not None
    assert event.originally_requested_gate == "cannot-pass"
    assert tp == 1


@pytest.mark.unit
def test_model_fallback_requires_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    config = load_profile("vast-single-gpu")
    tiny = HardwareSnapshot(
        gpu_count=1,
        gpus=[GpuDevice(index=0, name="NVIDIA GeForce GTX 1060", vram_mib=6144)],
        source="test",
    )
    report = validate_topology(config, tiny)
    model, event = maybe_model_fallback(config, report)
    assert event is None
    assert model.model_id == "Qwen/Qwen3.5-9B"
    monkeypatch.setenv("ALLOW_MODEL_FALLBACK", "true")
    config = load_profile("vast-single-gpu")
    model, event = maybe_model_fallback(config, report)
    assert event is not None
    assert model.model_id == "Qwen/Qwen2.5-1.5B-Instruct-AWQ"


@pytest.mark.unit
def test_heterogeneous_gpus_warn() -> None:
    config = load_profile("vast-single-gpu")
    hardware = HardwareSnapshot(
        gpu_count=2,
        gpus=[
            GpuDevice(index=0, name="NVIDIA GeForce RTX 3090", vram_mib=24576),
            GpuDevice(index=1, name="NVIDIA GeForce RTX 3080", vram_mib=10240),
        ],
        source="test",
    )
    report = validate_topology(config, hardware)
    assert any(issue.code == "heterogeneous-gpus" for issue in report.issues)


@pytest.mark.unit
def test_k8s_replica_rejects_ray_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COMPUTE_PROFILE", raising=False)
    monkeypatch.delenv("MODEL_CONFIG", raising=False)
    monkeypatch.setenv("DISTRIBUTED_EXECUTOR_BACKEND", "ray")
    config = load_profile("vast-k3s-replica")
    report = validate_topology(config, _one_gpu())
    assert not report.ok
    assert any(issue.code == "k8s-no-ray" for issue in report.issues)


@pytest.mark.unit
def test_k8s_replica_rejects_tp2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COMPUTE_PROFILE", raising=False)
    monkeypatch.delenv("MODEL_CONFIG", raising=False)
    monkeypatch.setenv("VLLM_TENSOR_PARALLEL_SIZE", "2")
    config = load_profile("vast-k3s-replica")
    report = validate_topology(config, _one_gpu())
    assert not report.ok
    assert any(issue.code in {"k8s-parallelism", "tp-exceeds-gpus"} for issue in report.issues)


@pytest.mark.unit
def test_ray_multinode_without_two_nodes() -> None:
    from inference_platform.config import ComputeConfig, load_yaml
    from inference_platform.paths import configs_dir

    config = load_profile("authoring")
    compute = ComputeConfig.model_validate(
        load_yaml(configs_dir() / "compute" / "ray-multinode.yaml")
    )
    config = config.model_copy(update={"compute": compute})
    report = validate_topology(config, _one_gpu())
    assert not report.ok
    assert any(issue.code == "multinode-unavailable" for issue in report.issues)
