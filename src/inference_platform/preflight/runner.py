"""Preflight CLI. Exit 0 only when no check FAILs."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from inference_platform.config import EnvSettings, default_profile_id, load_local_env, load_profile
from inference_platform.paths import artifacts_dir
from inference_platform.preflight.checks import run_local_checks
from inference_platform.preflight.results import CheckResult, Status
from inference_platform.secrets import redact_mapping

STATUS_ORDER: dict[Status, int] = {"FAIL": 0, "WARN": 1, "SKIP": 2, "PASS": 3}


def overall_status(results: list[CheckResult]) -> Status:
    if any(item.status == "FAIL" for item in results):
        return "FAIL"
    if any(item.status == "WARN" for item in results):
        return "WARN"
    if any(item.status == "PASS" for item in results):
        return "PASS"
    return "SKIP"


def print_human(results: list[CheckResult], profile: str) -> None:
    print(f"preflight profile={profile}")
    for item in results:
        extra = (
            f" — {item.remediation}" if item.remediation and item.status in {"FAIL", "WARN"} else ""
        )
        print(f"[{item.status:<4}] {item.name}: {item.summary}{extra}")
    print(f"overall={overall_status(results)}")


def write_report(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Environment preflight")
    parser.add_argument(
        "--profile", default=None, help="Composed profile id, e.g. authoring or vast-single-gpu"
    )
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text")
    parser.add_argument("--report", default=None, help="Write machine-readable JSON report path")
    args = parser.parse_args(argv)

    load_local_env()
    env = EnvSettings()
    profile_id = args.profile or default_profile_id()
    config = load_profile(profile_id, env)
    results = run_local_checks(config)
    status = overall_status(results)
    payload = redact_mapping(
        {
            "generated_at": datetime.now(UTC).isoformat(),
            "profile": profile_id,
            "provider": env.gpu_provider or config.profile.provider,
            "compute": None if config.compute is None else config.compute.id,
            "overall": status,
            "config": config.public_dict(),
            "checks": [item.as_dict() for item in results],
            "gate": {
                "phase": 0,
                "gpu_gate_claimed": False,
                "remote_executed": False,
                "note": (
                    "Phase 0 local authoring preflight. CUDA/vLLM acceptance is not claimed. "
                    "Remote SSH was not executed."
                ),
            },
        }
    )
    report_path = (
        Path(args.report) if args.report else artifacts_dir() / "phase0" / "preflight.json"
    )
    write_report(payload, report_path)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print_human(results, profile_id)
        print(f"report={report_path}")
    return 0 if status != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
