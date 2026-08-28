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
        "infra/kubernetes/base/deployment.yaml",
        "infra/kubernetes/base/service.yaml",
        "docs/runbooks/vast-k3s-rental.md",
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
def test_no_training_modules_imported() -> None:
    src = repo_root() / "src"
    blob = "\n".join(p.read_text(encoding="utf-8") for p in src.rglob("*.py"))
    for needle in ("Trainer", "fine-tune", "pretrain", "backward(", "optimizer.step"):
        assert needle not in blob
