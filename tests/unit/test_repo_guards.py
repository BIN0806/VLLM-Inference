"""Guardrails: no live hosts, secrets, or private briefs in the published tree."""

from __future__ import annotations

import subprocess

import pytest

from inference_platform.paths import repo_root

UNTRACKED_PATHS = (
    "distributed-llm-inference-agent-blueprint.md",
    ".env.local",
    ".ssh/known_hosts",
    "infra/keda/README.md",
    "infra/ray/README.md",
    "infra/observability/README.md",
    "infra/kubernetes/README.md",
    "infra/kubernetes/overlays/local/README.md",
    "infra/kubernetes/overlays/eks/README.md",
    "infra/kubernetes/overlays/gke/README.md",
    "docs/phase0-status.md",
    "docs/phase1-status.md",
    "docs/phase2-preflight.md",
    "docs/phase2-status.md",
    "docs/phase2b-status.md",
    "docs/phase3-plan.md",
    "docs/phase3-status.md",
    "docs/phase4-plan.md",
    "docs/phase4-preflight.md",
    "artifacts/phase3/closeout.json",
)


def _tracked_files() -> set[str]:
    root = repo_root()
    output = subprocess.check_output(["git", "ls-files"], cwd=root, text=True)
    return {line.strip() for line in output.splitlines() if line.strip()}


@pytest.mark.unit
def test_committed_tree_has_no_live_ssh_host() -> None:
    root = repo_root()
    forbidden = (
        ".".join(["137", "175", "76", "24"]),
        ".".join(["115", "246", "55", "147"]),
        "490" + "46059",
        "SHA256:" + "+jO/" + "pb36koT",
        ".".join(["76", "27", "73", "50"]),
        "490" + "70276",
        "SHA256:" + "/C2/" + "CgZ6l3AWEMja",
        "SHA256:" + "fmRdNclebn53",
        "certificate-" + "authority-data",
        "BEGIN " + "OPENSSH PRIVATE KEY",
        "BEGIN " + "RSA PRIVATE KEY",
        "BEGIN " + "CERTIFICATE",
    )
    for rel in sorted(_tracked_files()):
        path = root / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for needle in forbidden:
            assert needle not in text, f"sensitive material {needle!r} found in {rel}"


@pytest.mark.unit
def test_sensitive_and_wip_paths_are_untracked() -> None:
    tracked = _tracked_files()
    for rel in UNTRACKED_PATHS:
        assert rel not in tracked, f"{rel} must not be committed"
    for rel in tracked:
        name = rel.rsplit("/", 1)[-1]
        if rel.startswith("docs/") and (name.startswith("phase") or name.endswith("plan.md")):
            raise AssertionError(f"{rel} must not be committed")


@pytest.mark.unit
def test_model_layer_yaml_is_tracked() -> None:
    tracked = _tracked_files()
    for rel in (
        "configs/models/qwen3.5-9b.yaml",
        "configs/models/qwen2.5-1.5b-instruct-awq.yaml",
        "configs/profiles/vast-k3s-replica.yaml",
        "configs/profiles/vast-k3s-replica-9b.yaml",
        "configs/profiles/vast-k3s-replicas.yaml",
        "configs/compute/k8s-replicas.yaml",
        "configs/serving/k8s-replicas.yaml",
        "infra/kubernetes/base/deployment.yaml",
        "infra/kubernetes/base/service.yaml",
        "infra/kubernetes/overlays/vast-k3s-replicas/statefulset.yaml",
        "infra/kubernetes/overlays/vast-k3s-replicas/servicemonitor.yaml",
        "infra/observability/kube-prometheus-stack-values.yaml",
        "infra/observability/promql/vllm-acceptance.yaml",
        "infra/keda/scaledobject-vllm.yaml",
        "infra/keda/scaledobject-vllm-prometheus.yaml",
        "infra/keda/interceptorroute-vllm.yaml",
        "infra/keda/http-add-on-values.yaml",
        "infra/keda/servicemonitor-http-addon.yaml",
        "docs/runbooks/k3s-replicas-http.md",
        "docs/runbooks/k3s-replicas-http-status.md",
        "docs/decisions/0009-phase4c-http-interceptor-scale-to-zero.md",
        "docs/runbooks/vast-k3s-rental.md",
        "docs/runbooks/k3s-nvidia.md",
        "docs/runbooks/k3s-replicas-prometheus.md",
        "docs/runbooks/k3s-replicas-prometheus-status.md",
        "docs/runbooks/k3s-replicas-keda.md",
        "docs/runbooks/k3s-replicas-keda-status.md",
        "docs/decisions/0008-phase4b-keda-waiting-queue.md",
        "docs/runbooks/k3s-nvidia.md",
        "docs/decisions/0006-phase3-1.5b-disk-exception.md",
        "docs/runbooks/k3s-replica-1.5b-status.md",
        "infra/kubernetes/overlays/vast-k3s/runtime-class-patch.yaml",
        "infra/kubernetes/overlays/vast-k3s/nvidia-device-plugin-k3s-patch.yaml",
    ):
        assert rel in tracked, f"{rel} must be committed so clones can load profiles"


@pytest.mark.unit
def test_k3s_replica_status_records_out_of_scope() -> None:
    text = (repo_root() / "docs/runbooks/k3s-replica-1.5b-status.md").read_text(encoding="utf-8")
    assert "enableServiceLinks: false" in text
    assert "local-path" in text
    assert "does not survive destruction" in text.lower() or "deletes the PVC" in text
    for topic in ("9B", "Ray", "Prometheus", "KEDA", "scale-to-zero"):
        assert topic in text
    assert "not tested" in text.lower()


@pytest.mark.unit
def test_k3s_replicas_prometheus_status_records_latency_caveat() -> None:
    text = (repo_root() / "docs/runbooks/k3s-replicas-prometheus-status.md").read_text(
        encoding="utf-8"
    )
    assert "enableServiceLinks: false" in text
    assert "local-path" in text
    assert "does not survive" in text.lower() or "deletes the PVC" in text
    assert "not a valid latency comparison" in text
    assert "_count" in text and "_sum" in text
    assert "observability validation" in text.lower()
    assert "firewalled" in text.lower()
    assert "not" in text.lower() and "public" in text.lower()
    assert "ClusterIP-only" not in text
    for topic in ("9B", "Ray", "KEDA", "scale-to-zero"):
        assert topic in text
    assert "not tested" in text.lower()


@pytest.mark.unit
def test_k3s_replicas_keda_status_records_value_metric_and_boundary() -> None:
    text = (repo_root() / "docs/runbooks/k3s-replicas-keda-status.md").read_text(encoding="utf-8")
    assert "metricType: Value" in text
    assert "sum(vllm:num_requests_waiting)" in text
    assert "ignoreNullValues" in text
    assert "StatefulSet" in text
    assert "minReplicaCount: 1" in text
    assert "HTTP add-on" in text
    assert "not installed" in text.lower()
    assert "local-path" in text
    assert "die with the VM" in text
    for topic in ("9B", "scale-to-zero"):
        assert topic in text
    assert "not tested" in text.lower()
    assert "Connection: close" in text
    assert "not a valid latency comparison" in text
    assert "port-forward" in text.lower()
    assert "headless" in text.lower()
    assert "270" in text
    assert "55%" in text and "45%" in text
    assert "no measured client error rate" in text.lower()
    assert "1.03" in text and "2.03" in text
    assert "391" in text and "778" in text


@pytest.mark.unit
def test_k3s_replicas_http_status_records_lab_scale_to_zero() -> None:
    text = (repo_root() / "docs/runbooks/k3s-replicas-http-status.md").read_text(encoding="utf-8")
    assert "InterceptorRoute" in text
    assert "http.keda.sh/v1beta1" in text
    assert "external-push" in text
    assert "minReplicaCount: 0" in text
    assert "X-KEDA-HTTP-Cold-Start" in text
    assert "true" in text.lower()
    assert "152.426" in text
    assert "150-second" in text or "150 s" in text or "**150 s**" in text
    assert "did **not** retry" in text or "did not retry" in text.lower()
    assert "[DONE]" in text
    assert "valid" in text.lower() and "sse" in text.lower()
    assert "327" in text
    assert "phase4c-ordinal0-cache" in text
    assert "0.15.0" in text
    assert "exactly one" in text.lower()
    assert "HTTPScaledObject" in text
    assert "single-node lab" in text.lower()
    assert "one" in text.lower() and "interceptor" in text.lower()
    assert "beta" in text.lower()
    assert "not" in text.lower() and "production" in text.lower()
    assert "port-forward" in text.lower()
    assert "0→2 was not tested" in text
    assert "Prometheus-driven" in text and "1→2" in text
    assert "interceptor-driven" in text and "0→1" in text
    for topic in ("9B", "Ingress", "NodePort", "LoadBalancer"):
        assert topic in text
    assert "not tested" in text.lower() or "not claimed" in text.lower()


@pytest.mark.unit
def test_no_training_modules_imported() -> None:
    src = repo_root() / "src"
    blob = "\n".join(p.read_text(encoding="utf-8") for p in src.rglob("*.py"))
    for needle in ("Trainer", "fine-tune", "pretrain", "backward(", "optimizer.step"):
        assert needle not in blob
