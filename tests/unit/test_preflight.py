"""Preflight unit tests. These must not allocate a GPU or open SSH."""

from __future__ import annotations

from pathlib import Path

import pytest

from inference_platform.config import load_profile
from inference_platform.preflight.checks import check_python, check_remote_guard, run_local_checks
from inference_platform.preflight.results import CheckResult
from inference_platform.preflight.runner import main, overall_status


@pytest.mark.unit
def test_python_check_passes_on_supported_runtime() -> None:
    result = check_python()
    assert result.status == "PASS"
    assert result.name == "python"


@pytest.mark.unit
def test_authoring_preflight_has_no_fail_for_missing_nvidia() -> None:
    config = load_profile("authoring")
    results = run_local_checks(config)
    nvidia = next(item for item in results if item.name == "nvidia-local")
    assert nvidia.status in {"SKIP", "PASS"}
    k8s = next(item for item in results if item.name == "kubernetes")
    assert k8s.status == "SKIP"
    ray = next(item for item in results if item.name == "ray")
    assert ray.status == "SKIP"


@pytest.mark.unit
def test_remote_guard_skips_without_allow_flag() -> None:
    config = load_profile("vast-single-gpu")
    result = check_remote_guard(config)
    assert result.status == "SKIP"
    assert "INFERENCE_ALLOW_REMOTE" in (result.remediation or result.summary)


@pytest.mark.unit
def test_overall_fail_wins() -> None:
    results = [
        CheckResult("a", "PASS", "ok"),
        CheckResult("b", "FAIL", "bad", remediation="fix it"),
        CheckResult("c", "WARN", "meh"),
    ]
    assert overall_status(results) == "FAIL"


@pytest.mark.unit
def test_runner_writes_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report = tmp_path / "preflight.json"
    code = main(["--profile", "authoring", "--report", str(report)])
    assert code == 0
    text = report.read_text(encoding="utf-8")
    assert '"phase": 0' in text
    assert '"gpu_gate_claimed": false' in text
    assert "VLLM_API_KEY" not in text or "***REDACTED***" in text
    captured = capsys.readouterr().out
    assert "preflight profile=authoring" in captured
