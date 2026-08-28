"""CLI for Kubernetes host preflight. Does not install or apply anything."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
from datetime import UTC, datetime
from pathlib import Path

from inference_platform.config import EnvSettings, load_local_env, load_profile
from inference_platform.paths import artifacts_dir
from inference_platform.preflight.k8s_host import K8sHostFacts, evaluate_k8s_host
from inference_platform.preflight.runner import overall_status, print_human, write_report
from inference_platform.secrets import redact_mapping


def discover_k8s_host_facts() -> K8sHostFacts:
    """Best-effort local probe. Never starts services."""

    nvidia = shutil.which("nvidia-smi")
    gpu_names: list[str] = []
    gpu_vram: list[int] = []
    driver = None
    if nvidia:
        import subprocess

        proc = subprocess.run(
            [
                nvidia,
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3:
                    gpu_names.append(parts[0])
                    gpu_vram.append(int(float(parts[1])))
                    driver = parts[2]
    disk = shutil.disk_usage("/")
    ram = None
    try:
        import psutil

        ram = round(psutil.virtual_memory().total / (1024**3), 2)
    except Exception:
        ram = None
    return K8sHostFacts(
        systemd=Path("/run/systemd/system").exists(),
        uid=os.geteuid() if hasattr(os, "geteuid") else None,
        disk_total_gib=round(disk.total / (1024**3), 2),
        disk_free_gib=round(disk.free / (1024**3), 2),
        ram_gib=ram,
        gpu_count=len(gpu_names),
        gpu_names=gpu_names,
        gpu_vram_mib=gpu_vram,
        driver_version=driver,
        containerd=shutil.which("containerd") is not None or Path("/run/containerd").exists(),
        docker=shutil.which("docker") is not None,
        nvidia_container_runtime=shutil.which("nvidia-container-runtime") is not None
        or Path("/usr/bin/nvidia-container-runtime").exists(),
        kubernetes_available=False,
        k3s_active=Path("/etc/systemd/system/k3s.service").exists(),
        kubectl_nodes=None,
        nvidia_gpu_allocatable=None,
        source="local-probe",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase 3 Kubernetes host preflight (offline facts OK)"
    )
    parser.add_argument("--profile", default=None)
    parser.add_argument("--facts", default=None, help="JSON file of K8sHostFacts")
    parser.add_argument(
        "--require-cluster",
        action="store_true",
        help="FAIL if k3s/kubectl/NVIDIA runtime are missing. Default is host OS only.",
    )
    parser.add_argument(
        "--allow-env-topology",
        action="store_true",
        help="Honor COMPUTE_PROFILE/MODEL_CONFIG/TP/backend env overrides (off by default)",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--report", default=None)
    args = parser.parse_args(argv)

    load_local_env()
    if not args.allow_env_topology:
        for key in (
            "COMPUTE_PROFILE",
            "MODEL_CONFIG",
            "DISTRIBUTED_EXECUTOR_BACKEND",
            "VLLM_TENSOR_PARALLEL_SIZE",
            "VLLM_PIPELINE_PARALLEL_SIZE",
            "VLLM_MODEL",
            "SERVED_MODEL_NAME",
            "MODEL_REVISION",
        ):
            os.environ.pop(key, None)
    env = EnvSettings()
    profile_id = args.profile or os.environ.get("INFERENCE_PROFILE") or "vast-k3s-replica"
    config = load_profile(profile_id, env)

    if args.facts:
        data = json.loads(Path(args.facts).read_text(encoding="utf-8"))
        facts = K8sHostFacts.from_mapping(data)
    elif platform.system() != "Linux":
        print(
            "k8s-host preflight skipped: this is not a Linux GPU host. "
            "Pass --facts to evaluate a captured snapshot."
        )
        return 0
    else:
        facts = discover_k8s_host_facts()

    results = evaluate_k8s_host(config, facts, require_cluster=args.require_cluster)
    status = overall_status(results)
    payload = redact_mapping(
        {
            "generated_at": datetime.now(UTC).isoformat(),
            "profile": profile_id,
            "overall": status,
            "require_cluster": args.require_cluster,
            "model_id": config.model_id,
            "checks": [item.as_dict() for item in results],
            "gate": {
                "phase": 3,
                "gpu_gate_claimed": False,
                "cluster_claimed": False,
                "note": "Offline/host preflight only. No rental, k3s, or apply was performed.",
            },
        }
    )
    report_path = (
        Path(args.report) if args.report else artifacts_dir() / "phase3" / "k8s-host-preflight.json"
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
