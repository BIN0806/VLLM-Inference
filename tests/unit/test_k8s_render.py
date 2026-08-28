"""Offline Kubernetes manifest rendering tests. No cluster required."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from inference_platform.config import load_profile
from inference_platform.k8s.render import RenderError, render_manifests, write_manifests


@pytest.fixture(autouse=True)
def _isolate_k8s_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "COMPUTE_PROFILE",
        "MODEL_CONFIG",
        "VLLM_TENSOR_PARALLEL_SIZE",
        "VLLM_PIPELINE_PARALLEL_SIZE",
        "DISTRIBUTED_EXECUTOR_BACKEND",
        "ALLOW_MODEL_FALLBACK",
        "ALLOW_TP_FALLBACK",
        "K8S_NAMESPACE",
        "K8S_PVC_SIZE",
        "K8S_STORAGE_CLASS",
        "K8S_MODEL_CACHE_PATH",
        "VLLM_MAX_MODEL_LEN",
        "VLLM_MAX_NUM_SEQS",
        "VLLM_GPU_MEMORY_UTILIZATION",
        "VLLM_IMAGE",
        "VLLM_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.unit
def test_vast_k3s_replica_uses_portable_baseline() -> None:
    config = load_profile("vast-k3s-replica")
    assert config.compute is not None
    assert config.compute.id == "k8s-replica"
    assert config.model.model_id == "Qwen/Qwen2.5-1.5B-Instruct-AWQ"
    assert config.tensor_parallel_size == 1
    assert config.distributed_executor_backend == "mp"
    assert config.fallback_model is None


@pytest.mark.unit
def test_render_requests_one_gpu_and_slow_probes() -> None:
    manifests = render_manifests(load_profile("vast-k3s-replica"))
    deployment = manifests["deployment.yaml"]
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["resources"]["limits"]["nvidia.com/gpu"] == "1"
    assert container["resources"]["requests"]["nvidia.com/gpu"] == "1"
    assert container["startupProbe"]["failureThreshold"] == 90
    assert container["startupProbe"]["periodSeconds"] == 10
    assert container["readinessProbe"]["httpGet"]["path"] == "/health"
    assert container["livenessProbe"]["httpGet"]["path"] == "/health"
    assert "ray" not in " ".join(container["args"]).lower()
    assert "--quantization" in container["args"]
    assert "awq" in container["args"]
    spec = deployment["spec"]["template"]["spec"]
    assert spec.get("hostNetwork") is not True
    assert "hostPort" not in str(container["ports"])
    assert manifests["service.yaml"]["spec"]["type"] == "ClusterIP"
    secret = manifests["secret.yaml.example"]["stringData"]
    assert secret["HF_TOKEN"] == ""
    assert secret["VLLM_API_KEY"] == ""
    assert "sha256:" in container["image"]
    assert "latest" not in container["image"]
    notes = manifests["storage.yaml"]["data"]["notes"]
    assert "persists across pod restarts" in notes
    assert "does not survive destruction of the Vast VM" in notes
    assert "not provider-persistent" in notes


@pytest.mark.unit
def test_render_is_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VLLM_MAX_MODEL_LEN", "4096")
    monkeypatch.setenv("VLLM_MAX_NUM_SEQS", "4")
    monkeypatch.setenv("VLLM_GPU_MEMORY_UTILIZATION", "0.85")
    monkeypatch.setenv("K8S_NAMESPACE", "lab")
    monkeypatch.setenv("K8S_PVC_SIZE", "60Gi")
    monkeypatch.setenv("K8S_STORAGE_CLASS", "fast")
    monkeypatch.setenv("K8S_MODEL_CACHE_PATH", "/models")
    config = load_profile("vast-k3s-replica")
    manifests = render_manifests(config)
    data = manifests["configmap.yaml"]["data"]
    assert data["MAX_MODEL_LEN"] == "4096"
    assert data["MAX_NUM_SEQS"] == "4"
    assert data["GPU_MEMORY_UTILIZATION"] == "0.85"
    assert data["MODEL_CACHE_PATH"] == "/models"
    assert data["STORAGE_CLASS"] == "fast"
    assert data["PVC_SIZE"] == "60Gi"
    assert manifests["namespace.yaml"]["metadata"]["name"] == "lab"
    assert manifests["pvc.yaml"]["spec"]["resources"]["requests"]["storage"] == "60Gi"
    mount = manifests["deployment.yaml"]["spec"]["template"]["spec"]["containers"][0][
        "volumeMounts"
    ][0]
    assert mount["mountPath"] == "/models"


@pytest.mark.unit
def test_render_refuses_ray_and_tp_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISTRIBUTED_EXECUTOR_BACKEND", "ray")
    with pytest.raises(RenderError, match="Ray"):
        render_manifests(load_profile("vast-k3s-replica"))
    monkeypatch.delenv("DISTRIBUTED_EXECUTOR_BACKEND")
    monkeypatch.setenv("ALLOW_MODEL_FALLBACK", "true")
    with pytest.raises(RenderError, match="ALLOW_MODEL_FALLBACK"):
        render_manifests(load_profile("vast-k3s-replica"))


@pytest.mark.unit
def test_render_refuses_authoring_profile() -> None:
    with pytest.raises(RenderError):
        render_manifests(load_profile("authoring"))


@pytest.mark.unit
def test_write_manifests(tmp_path: Path) -> None:
    written = write_manifests(load_profile("vast-k3s-replica"), tmp_path)
    names = {path.name for path in written}
    assert "deployment.yaml" in names
    assert "secret.yaml.example" in names
    kustomize = yaml.safe_load((tmp_path / "kustomization.yaml").read_text())
    assert "secret.yaml.example" not in kustomize["resources"]


@pytest.mark.unit
def test_vast_k3s_overlay_sets_nvidia_runtime_class() -> None:
    from inference_platform.paths import repo_root

    overlay = repo_root() / "infra" / "kubernetes" / "overlays" / "vast-k3s"
    kustomize = yaml.safe_load((overlay / "kustomization.yaml").read_text())
    assert "runtime-class-patch.yaml" in kustomize["patches"][0]["path"]
    patch = yaml.safe_load((overlay / "runtime-class-patch.yaml").read_text())
    assert patch["spec"]["template"]["spec"]["runtimeClassName"] == "nvidia"
    plugin = yaml.safe_load((overlay / "nvidia-device-plugin-k3s-patch.yaml").read_text())
    assert plugin["spec"]["template"]["spec"]["runtimeClassName"] == "nvidia"
