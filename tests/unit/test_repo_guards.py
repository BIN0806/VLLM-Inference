"""Guardrails: no live hosts or training stacks in committed config."""

from __future__ import annotations

import pytest

from inference_platform.paths import repo_root


@pytest.mark.unit
def test_committed_tree_has_no_live_ssh_host() -> None:
    root = repo_root()
    roots = [
        root / "configs",
        root / "docker",
        root / "src",
        root / "scripts",
        root / "docs",
        root / "infra",
        root / ".github",
        root / ".env.example",
        root / "compose.yaml",
        root / "Makefile",
        root / "README.md",
        root / "pyproject.toml",
    ]
    live_host = ".".join(["137", "175", "76", "24"])
    for path in roots:
        files = [path] if path.is_file() else path.rglob("*")
        for file_path in files:
            if not file_path.is_file():
                continue
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            assert live_host not in text, f"live SSH host found in {file_path}"
            assert "BEGIN OPENSSH PRIVATE KEY" not in text
            assert "BEGIN RSA PRIVATE KEY" not in text


@pytest.mark.unit
def test_no_training_modules_imported() -> None:
    src = repo_root() / "src"
    blob = "\n".join(p.read_text(encoding="utf-8") for p in src.rglob("*.py"))
    for needle in ("Trainer", "fine-tune", "pretrain", "backward(", "optimizer.step"):
        assert needle not in blob
