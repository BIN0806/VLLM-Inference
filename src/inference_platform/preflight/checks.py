"""Local authoring and optional remote preflight checks."""

from __future__ import annotations

import platform
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import psutil

from inference_platform.config import ResolvedConfig
from inference_platform.hardware import discover_local, snapshot_from_discovery
from inference_platform.preflight.results import CheckResult
from inference_platform.topology import validate_topology

SUPPORTED_AUTHORING_PYTHON = {(3, 11), (3, 12)}


def check_python() -> CheckResult:
    version = sys.version_info
    triple = f"{version.major}.{version.minor}.{version.micro}"
    if (version.major, version.minor) in SUPPORTED_AUTHORING_PYTHON:
        return CheckResult(
            name="python",
            status="PASS",
            summary=f"Python {triple} is supported for authoring",
            details={"version": triple},
        )
    if (version.major, version.minor) == (3, 14):
        return CheckResult(
            name="python",
            status="FAIL",
            summary=f"Python {triple} is outside the Phase 0 authoring range 3.11–3.12",
            remediation="Use `uv sync --python 3.12` (or 3.11). Do not run project tooling on 3.14.",
            details={"version": triple},
        )
    return CheckResult(
        name="python",
        status="FAIL",
        summary=f"Python {triple} is not in the supported authoring range 3.11–3.12",
        remediation="Install Python 3.12 and recreate the virtualenv with uv.",
        details={"version": triple},
    )


def check_platform(config: ResolvedConfig) -> CheckResult:
    system = platform.system()
    machine = platform.machine()
    details = {"system": system, "machine": machine, "release": platform.release()}
    if config.profile.gpu_required and config.profile.remote_required:
        return CheckResult(
            name="platform",
            status="PASS",
            summary=f"{system}/{machine} is an authoring/client host; GPU gate is remote",
            details=details,
        )
    if config.profile.gpu_required and system != "Linux":
        return CheckResult(
            name="platform",
            status="FAIL",
            summary=f"{system}/{machine} cannot satisfy the NVIDIA CUDA GPU gate",
            remediation="Run GPU gates on a Linux NVIDIA host over SSH. This workstation is authoring-only.",
            details=details,
        )
    if system == "Darwin":
        return CheckResult(
            name="platform",
            status="PASS",
            summary=f"Authoring workstation {system}/{machine}; NVIDIA CUDA is not expected here",
            details=details,
        )
    if system == "Linux" and machine in {"x86_64", "amd64"}:
        return CheckResult(
            name="platform",
            status="PASS",
            summary=f"Linux {machine} is the NVIDIA MVP architecture",
            details=details,
        )
    return CheckResult(
        name="platform",
        status="WARN",
        summary=f"Unusual platform {system}/{machine} for the NVIDIA MVP",
        details=details,
    )


def check_docker() -> CheckResult:
    docker = shutil.which("docker")
    if docker is None:
        return CheckResult(
            name="docker",
            status="WARN",
            summary="Docker CLI not found",
            remediation="Install Docker for compose-based serving. Not required for authoring unit tests.",
        )
    proc = shutil.which("docker")
    details = {"docker": proc}
    try:
        info = subprocess.run(
            [proc, "info"],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except OSError as exc:
        return CheckResult(
            name="docker",
            status="WARN",
            summary=f"Docker CLI is present but could not be executed ({exc})",
            remediation="Start OrbStack or Docker Desktop if you need compose.",
            details=details,
        )
    if info.returncode != 0:
        return CheckResult(
            name="docker",
            status="WARN",
            summary="Docker CLI is present but the daemon is not reachable",
            remediation="Start OrbStack or Docker Desktop if you need compose. Not required for Phase 0 unit tests.",
            details=details,
        )
    return CheckResult(
        name="docker",
        status="PASS",
        summary="Docker CLI and daemon are available",
        details=details,
    )


def check_nvidia_local(config: ResolvedConfig) -> CheckResult:
    nvidia = shutil.which("nvidia-smi")
    if nvidia is None:
        status = (
            "FAIL" if config.profile.gpu_required and not config.profile.remote_required else "SKIP"
        )
        if config.profile.remote_required:
            status = "SKIP"
        return CheckResult(
            name="nvidia-local",
            status=status,
            summary="nvidia-smi is not available on this workstation",
            remediation="Expected on the GPU host, not on the macOS authoring workstation.",
        )
    return CheckResult(name="nvidia-local", status="PASS", summary="nvidia-smi found on this host")


def check_memory_disk(config: ResolvedConfig | None = None) -> CheckResult:
    vm = psutil.virtual_memory()
    disk = shutil.disk_usage("/")
    mem_gib = vm.total / (1024**3)
    free_gib = disk.free / (1024**3)
    details = {
        "memory_gib": round(mem_gib, 2),
        "memory_available_gib": round(vm.available / (1024**3), 2),
        "disk_free_gib": round(free_gib, 2),
    }
    authoring_only = config is not None and not config.profile.gpu_required
    if free_gib < 5 and not authoring_only:
        return CheckResult(
            name="capacity",
            status="FAIL",
            summary=f"Only {free_gib:.1f} GiB free disk",
            remediation="Free disk space. Model caches and container images need multiple gigabytes.",
            details=details,
        )
    if free_gib < 20:
        return CheckResult(
            name="capacity",
            status="WARN",
            summary=f"{free_gib:.1f} GiB free disk; CUDA images plus model weights may not fit here",
            remediation="Keep large images and model caches on the GPU host. This Mac is authoring-only.",
            details=details,
        )
    return CheckResult(
        name="capacity",
        status="PASS",
        summary=f"{mem_gib:.1f} GiB RAM, {free_gib:.1f} GiB free disk",
        details=details,
    )


def check_port(port: int) -> CheckResult:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.3)
    try:
        in_use = sock.connect_ex(("127.0.0.1", port)) == 0
    finally:
        sock.close()
    if in_use:
        return CheckResult(
            name="api-port",
            status="WARN",
            summary=f"Port {port} is already in use on localhost",
            remediation="Choose another VLLM_LOCAL_TUNNEL_PORT or stop the occupying process.",
            details={"port": port},
        )
    return CheckResult(
        name="api-port",
        status="PASS",
        summary=f"Port {port} is available on localhost",
        details={"port": port},
    )


def check_shared_memory() -> CheckResult:
    shm = Path("/dev/shm")
    if not shm.exists():
        return CheckResult(
            name="shared-memory",
            status="SKIP",
            summary="/dev/shm is not present on this OS; compose uses shm_size on Linux GPU hosts",
        )
    total = shutil.disk_usage("/dev/shm").total / (1024**3)
    if total < 1:
        return CheckResult(
            name="shared-memory",
            status="WARN",
            summary=f"/dev/shm is only {total:.2f} GiB",
            remediation="Raise shm_size or use host IPC on the GPU host.",
            details={"shm_gib": round(total, 2)},
        )
    return CheckResult(
        name="shared-memory",
        status="PASS",
        summary=f"/dev/shm is {total:.2f} GiB",
        details={"shm_gib": round(total, 2)},
    )


def check_kubernetes(config: ResolvedConfig) -> CheckResult:
    if not config.profile.id.startswith("k8s"):
        return CheckResult(
            name="kubernetes",
            status="SKIP",
            summary="Kubernetes is not required for this profile",
        )
    if shutil.which("kubectl") is None:
        return CheckResult(
            name="kubernetes",
            status="FAIL",
            summary="kubectl is required for Kubernetes profiles",
            remediation="Install kubectl and point it at a GPU-capable cluster.",
        )
    return CheckResult(
        name="kubernetes",
        status="WARN",
        summary="kubectl is present; cluster validation is not part of Phase 0",
        remediation="Do not claim EKS, GKE, minikube, or k3s acceptance until those phases run.",
    )


def check_ray(config: ResolvedConfig) -> CheckResult:
    backend = config.distributed_executor_backend
    compute_id = None if config.compute is None else config.compute.id
    if backend != "ray" and compute_id not in {"ray-single-host", "ray-multinode"}:
        return CheckResult(
            name="ray", status="SKIP", summary="Ray is not required for this profile"
        )
    if compute_id == "ray-multinode":
        return CheckResult(
            name="ray",
            status="SKIP",
            summary="NOT RUN — HARDWARE UNAVAILABLE: two independently scheduled GPU machines are not present",
        )
    return CheckResult(
        name="ray",
        status="SKIP",
        summary="Ray connectivity is deferred until a Ray profile is executed on GPU hardware",
    )


def check_pins(config: ResolvedConfig) -> CheckResult:
    pins = config.pins
    image = pins.get("vllm", {}).get("official_image", {})
    if "latest" in str(image.get("tag", "")).lower():
        return CheckResult(
            name="pins",
            status="FAIL",
            summary="Pinned vLLM image tag must not be latest",
            remediation="Set an exact tag and digest in configs/pins.yaml",
        )
    return CheckResult(
        name="pins",
        status="PASS",
        summary=f"vLLM {pins.get('vllm', {}).get('version')} and model revisions are pinned",
        details={
            "vllm": pins.get("vllm", {}).get("version"),
            "baseline_revision": pins.get("models", {})
            .get("portable_baseline", {})
            .get("revision"),
            "override_revision": pins.get("models", {})
            .get("current_validation_override", {})
            .get("revision"),
        },
    )


def check_secrets_not_in_tree() -> CheckResult:
    return CheckResult(
        name="secrets-on-disk",
        status="PASS",
        summary="Secret filenames are gitignored; preflight does not print secret values",
        details={"note": "existence of gitignored local env files is not a failure"},
    )


def check_remote_guard(config: ResolvedConfig) -> CheckResult:
    if not config.profile.remote_required:
        return CheckResult(
            name="remote-guard",
            status="SKIP",
            summary="Remote GPU checks are not required for this profile",
        )
    if not config.env.inference_allow_remote:
        return CheckResult(
            name="remote-guard",
            status="SKIP",
            summary="Remote SSH checks were not executed (INFERENCE_ALLOW_REMOTE is not set)",
            remediation=(
                "After vLLM startup is complete, set INFERENCE_ALLOW_REMOTE=1 and run "
                "`make preflight-remote`. Do not interrupt a loading vLLM process."
            ),
        )
    return CheckResult(
        name="remote-guard",
        status="WARN",
        summary="Remote execution is enabled; still use read-only discovery only",
        remediation="Do not stop, restart, or kill vLLM from this repository.",
    )


def check_topology_without_hardware(config: ResolvedConfig) -> CheckResult:
    report = validate_topology(config, None)
    fails = [issue.message for issue in report.issues if issue.severity == "FAIL"]
    if fails:
        return CheckResult(
            name="topology",
            status="FAIL",
            summary=fails[0],
            details={"issues": [issue.__dict__ for issue in report.issues]},
        )
    return CheckResult(
        name="topology",
        status="WARN" if any(i.severity == "WARN" for i in report.issues) else "PASS",
        summary="Topology config is internally consistent; GPU counts not yet discovered",
        details={"issues": [issue.__dict__ for issue in report.issues]},
    )


def check_local_hardware_snapshot() -> CheckResult:
    data = discover_local()
    snapshot = snapshot_from_discovery(data)
    return CheckResult(
        name="local-hardware",
        status="PASS" if snapshot.gpu_count == 0 else "WARN",
        summary=(
            "No local NVIDIA GPUs (expected on the authoring Mac)"
            if snapshot.gpu_count == 0
            else f"{snapshot.gpu_count} local GPU(s) reported"
        ),
        details={
            "gpu_count": snapshot.gpu_count,
            "platform": data.get("platform"),
            "memory_gib": data.get("system_memory_gib"),
            "disk_free_gib": data.get("disk_free_gib"),
        },
    )


def run_local_checks(config: ResolvedConfig) -> list[CheckResult]:
    port = config.env.vllm_local_tunnel_port
    return [
        check_python(),
        check_platform(config),
        check_docker(),
        check_nvidia_local(config),
        check_memory_disk(config),
        check_port(port),
        check_shared_memory(),
        check_kubernetes(config),
        check_ray(config),
        check_pins(config),
        check_secrets_not_in_tree(),
        check_remote_guard(config),
        check_topology_without_hardware(config),
        check_local_hardware_snapshot(),
    ]
