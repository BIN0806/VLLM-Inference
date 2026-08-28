"""Repository path helpers."""

from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "configs").is_dir():
            return candidate
    raise RuntimeError("Unable to locate repository root from inference_platform package")


def configs_dir() -> Path:
    return repo_root() / "configs"


def artifacts_dir() -> Path:
    path = repo_root() / "artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path
