"""Shared pytest fixtures. Default collection excludes GPU and cluster tests."""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "unit: no Docker, GPU, network, or cluster required")
