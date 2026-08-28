"""Kubernetes host preflight tests. No live cluster or GPU."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from inference_platform.config import load_profile
from inference_platform.preflight.k8s_host import K8sHostFacts, evaluate_k8s_host
from inference_platform.preflight.k8s_host_cli import main
from inference_platform.preflight.runner import overall_status


@pytest.fixture(autouse=True)
def _isolate_k8s_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "COMPUTE_PROFILE",
        "MODEL_CONFIG",
        "VLLM_TENSOR_PARALLEL_SIZE",
        "DISTRIBUTED_EXECUTOR_BACKEND",
        "ALLOW_MODEL_FALLBACK",
        "ALLOW_TP_FALLBACK",
        "VLLM_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)


def _good_24g(**overrides) -> K8sHostFacts:
    data = dict(
        systemd=True,
        uid=0,
        disk_total_gib=120,
        disk_free_gib=100,
        ram_gib=64,
        gpu_count=1,
        gpu_names=["NVIDIA GeForce RTX 3090"],
        gpu_vram_mib=[24576],
        driver_version="550.90.07",
        containerd=True,
        nvidia_container_runtime=True,
        kubernetes_available=True,
        k3s_active=True,
        kubectl_nodes=1,
        nvidia_gpu_allocatable=1,
        source="test",
    )
    data.update(overrides)
    return K8sHostFacts.from_mapping(data)


@pytest.mark.unit
def test_healthy_1_5b_facts_pass() -> None:
    results = evaluate_k8s_host(load_profile("vast-k3s-replica"), _good_24g())
    assert overall_status(results) in {"PASS", "WARN"}
    assert all(item.status != "FAIL" for item in results)


@pytest.mark.unit
def test_missing_systemd_fails() -> None:
    results = evaluate_k8s_host(load_profile("vast-k3s-replica"), _good_24g(systemd=False))
    systemd = next(item for item in results if item.name == "systemd")
    assert systemd.status == "FAIL"


@pytest.mark.unit
def test_small_disk_fails() -> None:
    results = evaluate_k8s_host(load_profile("vast-k3s-replica"), _good_24g(disk_total_gib=40))
    disk = next(item for item in results if item.name == "disk")
    assert disk.status == "FAIL"


@pytest.mark.unit
def test_1_5b_disk_exception_warns_when_free_space_meets_install_floor() -> None:
    facts = _good_24g(disk_total_gib=72.5, disk_free_gib=55.0)
    results = evaluate_k8s_host(
        load_profile("vast-k3s-replica"), facts, require_cluster=False, disk_gate="before_install"
    )
    disk = next(item for item in results if item.name == "disk")
    free = next(item for item in results if item.name == "disk-free")
    assert disk.status == "WARN"
    assert "preferably 100" in disk.summary
    assert "9B stays NO-GO" in disk.summary
    assert free.status == "PASS"
    assert overall_status(results) != "FAIL"


@pytest.mark.unit
def test_1_5b_disk_exception_fails_when_free_space_below_install_floor() -> None:
    facts = _good_24g(disk_total_gib=72.5, disk_free_gib=30.0)
    results = evaluate_k8s_host(
        load_profile("vast-k3s-replica"), facts, require_cluster=False, disk_gate="before_install"
    )
    free = next(item for item in results if item.name == "disk-free")
    assert free.status == "FAIL"
    assert "Do not silently delete" in (free.remediation or "")
    assert overall_status(results) == "FAIL"


@pytest.mark.unit
def test_1_5b_disk_exception_fails_when_free_space_below_acceptance_floor() -> None:
    facts = _good_24g(disk_total_gib=72.5, disk_free_gib=14.0)
    results = evaluate_k8s_host(
        load_profile("vast-k3s-replica"),
        facts,
        require_cluster=False,
        disk_gate="after_acceptance",
    )
    free = next(item for item in results if item.name == "disk-free")
    assert free.status == "FAIL"
    assert overall_status(results) == "FAIL"


@pytest.mark.unit
def test_9b_does_not_receive_the_1_5b_disk_exception() -> None:
    facts = _good_24g(disk_total_gib=72.5, disk_free_gib=55.0)
    results = evaluate_k8s_host(load_profile("vast-k3s-replica-9b"), facts, require_cluster=False)
    disk = next(item for item in results if item.name == "disk")
    assert disk.status == "FAIL"
    assert not any(item.name == "disk-free" for item in results)
    assert overall_status(results) == "FAIL"


@pytest.mark.unit
def test_9b_on_12gib_fails_closed() -> None:
    facts = _good_24g(gpu_names=["NVIDIA GeForce RTX 3060"], gpu_vram_mib=[12288])
    results = evaluate_k8s_host(load_profile("vast-k3s-replica-9b"), facts)
    fit = next(item for item in results if item.name == "model-fit")
    assert fit.status == "FAIL"
    assert overall_status(results) == "FAIL"


@pytest.mark.unit
def test_9b_on_24gib_does_not_switch_model() -> None:
    results = evaluate_k8s_host(load_profile("vast-k3s-replica-9b"), _good_24g())
    fit = next(item for item in results if item.name == "model-fit")
    assert fit.status != "FAIL"
    config = load_profile("vast-k3s-replica-9b")
    assert config.model.model_id == "Qwen/Qwen3.5-9B"
    assert config.fallback_model is None


@pytest.mark.unit
def test_require_cluster_false_skips_k8s_install_checks() -> None:
    facts = _good_24g(kubernetes_available=False, k3s_active=False, nvidia_container_runtime=False)
    results = evaluate_k8s_host(load_profile("vast-k3s-replica"), facts, require_cluster=False)
    kube = next(item for item in results if item.name == "kubernetes")
    assert kube.status == "SKIP"
    assert overall_status(results) != "FAIL"


@pytest.mark.unit
def test_cli_with_facts_file(tmp_path: Path) -> None:
    facts_path = tmp_path / "facts.json"
    facts_path.write_text(
        json.dumps(
            {
                "systemd": True,
                "uid": 0,
                "disk_total_gib": 120,
                "disk_free_gib": 90,
                "ram_gib": 32,
                "gpu_count": 1,
                "gpu_names": ["NVIDIA GeForce RTX 4090"],
                "gpu_vram_mib": [24576],
                "driver_version": "560.35.03",
                "containerd": True,
                "nvidia_container_runtime": True,
                "kubernetes_available": True,
                "k3s_active": True,
                "kubectl_nodes": 1,
                "nvidia_gpu_allocatable": 1,
            }
        ),
        encoding="utf-8",
    )
    report = tmp_path / "report.json"
    code = main(
        [
            "--profile",
            "vast-k3s-replica",
            "--facts",
            str(facts_path),
            "--require-cluster",
            "--report",
            str(report),
        ]
    )
    assert code == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["gate"]["gpu_gate_claimed"] is False
    assert payload["profile"] == "vast-k3s-replica"
