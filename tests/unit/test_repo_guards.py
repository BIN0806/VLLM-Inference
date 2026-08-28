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
)


def _tracked_files() -> set[str]:
    root = repo_root()
    output = subprocess.check_output(["git", "ls-files"], cwd=root, text=True)
    return {line.strip() for line in output.splitlines() if line.strip()}


@pytest.mark.unit
def test_committed_tree_has_no_live_ssh_host() -> None:
    root = repo_root()
    live_host = ".".join(["137", "175", "76", "24"])
    for rel in sorted(_tracked_files()):
        path = root / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert live_host not in text, f"live SSH host found in {rel}"
        assert "BEGIN " + "OPENSSH PRIVATE KEY" not in text
        assert "BEGIN " + "RSA PRIVATE KEY" not in text


@pytest.mark.unit
def test_sensitive_and_wip_paths_are_untracked() -> None:
    tracked = _tracked_files()
    for rel in UNTRACKED_PATHS:
        assert rel not in tracked, f"{rel} must not be committed"


@pytest.mark.unit
def test_no_training_modules_imported() -> None:
    src = repo_root() / "src"
    blob = "\n".join(p.read_text(encoding="utf-8") for p in src.rglob("*.py"))
    for needle in ("Trainer", "fine-tune", "pretrain", "backward(", "optimizer.step"):
        assert needle not in blob
