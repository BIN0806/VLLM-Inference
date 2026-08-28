"""Read-only hardware discovery. Does not import torch/vLLM (those can initialize CUDA)."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import psutil

from inference_platform.config import EnvSettings, load_local_env
from inference_platform.secrets import redact_mapping
from inference_platform.ssh import ssh_argv
from inference_platform.topology import GpuDevice, HardwareSnapshot

REMOTE_DISCOVERY_SCRIPT = r"""
set -eu
python3 - <<'PY'
import json, os, shutil, subprocess, sys
from pathlib import Path

def run(cmd):
    try:
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=20)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return 127, "", str(exc)

gpus = []
code, out, err = run(["nvidia-smi", "--query-gpu=index,name,memory.total,memory.free,driver_version", "--format=csv,noheader,nounits"])
driver = None
if code == 0 and out:
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue
        gpus.append({
            "index": int(parts[0]),
            "name": parts[1],
            "vram_mib": int(float(parts[2])),
            "free_vram_mib": int(float(parts[3])),
        })
        driver = parts[4]
code, topo, _ = run(["nvidia-smi", "topo", "-m"])
interconnect = topo if code == 0 else None
code, cuda_out, _ = run(["nvidia-smi"])
cuda = None
if code == 0:
    for line in cuda_out.splitlines():
        if "CUDA Version" in line:
            cuda = line.split("CUDA Version:")[-1].strip().split()[0]
            break

mem = None
meminfo = Path("/proc/meminfo")
if meminfo.is_file():
    for line in meminfo.read_text().splitlines():
        if line.startswith("MemAvailable:"):
            mem = round(int(line.split()[1]) / (1024 * 1024), 2)
            break

disk = round(shutil.disk_usage("/").free / (1024 ** 3), 2)
shm = None
shm_path = Path("/dev/shm")
if shm_path.exists():
    shm = round(shutil.disk_usage("/dev/shm").total / (1024 ** 3), 2)

packages = {}
for name in ("vllm", "ray", "torch"):
    code, out, _ = run([sys.executable, "-m", "pip", "show", name])
    version = None
    if code == 0:
        for line in out.splitlines():
            if line.lower().startswith("version:"):
                version = line.split(":", 1)[1].strip()
    packages[name] = version

print(json.dumps({
    "gpu_count": len(gpus),
    "gpus": gpus,
    "driver_version": driver,
    "cuda_reported": cuda,
    "cpu_count": os.cpu_count(),
    "system_memory_gib": mem,
    "disk_free_gib": disk,
    "shm_gib": shm,
    "interconnect": interconnect,
    "python": sys.version.split()[0],
    "packages": packages,
    "hostname": os.uname().nodename,
    "source": "remote-read-only",
}, indent=2))
PY
"""


def discover_local() -> dict[str, Any]:
    vm = psutil.virtual_memory()
    disk = shutil.disk_usage("/")
    gpus: list[dict[str, Any]] = []
    driver = None
    cuda = None
    interconnect = None
    nvidia = shutil.which("nvidia-smi")
    if nvidia:
        proc = subprocess.run(
            [
                nvidia,
                "--query-gpu=index,name,memory.total,memory.free,driver_version",
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
                if len(parts) < 5:
                    continue
                gpus.append(
                    {
                        "index": int(parts[0]),
                        "name": parts[1],
                        "vram_mib": int(float(parts[2])),
                        "free_vram_mib": int(float(parts[3])),
                    }
                )
                driver = parts[4]
        topo = subprocess.run(
            [nvidia, "topo", "-m"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        if topo.returncode == 0:
            interconnect = topo.stdout.strip()
    shm_gib = None
    shm = Path("/dev/shm")
    if shm.exists():
        shm_gib = round(shutil.disk_usage("/dev/shm").total / (1024**3), 2)
    return {
        "gpu_count": len(gpus),
        "gpus": gpus,
        "driver_version": driver,
        "cuda_reported": cuda,
        "cpu_count": os.cpu_count(),
        "cpu_model": platform.processor() or None,
        "system_memory_gib": round(vm.total / (1024**3), 2),
        "system_memory_available_gib": round(vm.available / (1024**3), 2),
        "disk_free_gib": round(disk.free / (1024**3), 2),
        "shm_gib": shm_gib,
        "interconnect": interconnect,
        "python": platform.python_version(),
        "platform": f"{platform.system()} {platform.release()} {platform.machine()}",
        "packages": {},
        "source": "local",
    }


def snapshot_from_discovery(data: dict[str, Any]) -> HardwareSnapshot:
    gpus = [
        GpuDevice(
            index=int(item.get("index", idx)),
            name=str(item["name"]),
            vram_mib=int(item["vram_mib"]),
            free_vram_mib=item.get("free_vram_mib"),
        )
        for idx, item in enumerate(data.get("gpus") or [])
    ]
    return HardwareSnapshot(
        gpu_count=int(data.get("gpu_count", len(gpus))),
        gpus=gpus,
        node_count=int(data.get("node_count", 1)),
        driver_version=data.get("driver_version"),
        cuda_reported=data.get("cuda_reported"),
        system_memory_gib=data.get("system_memory_gib"),
        disk_free_gib=data.get("disk_free_gib"),
        shm_gib=data.get("shm_gib"),
        interconnect=data.get("interconnect"),
        source=str(data.get("source", "discovery")),
    )


def discover_remote(env: EnvSettings | None = None) -> dict[str, Any]:
    env = env or EnvSettings()
    if not env.inference_allow_remote:
        raise PermissionError(
            "Remote discovery is disabled until INFERENCE_ALLOW_REMOTE=1 "
            "after vLLM startup is reported complete"
        )
    if not env.gpu_ssh_host or env.gpu_ssh_port is None:
        raise ValueError("GPU_SSH_HOST and GPU_SSH_PORT are required")
    from inference_platform.ssh import SSHTarget

    target = SSHTarget(
        host=env.gpu_ssh_host,
        port=env.gpu_ssh_port,
        user=env.gpu_ssh_user,
        known_hosts=env.gpu_ssh_known_hosts,
        identity_file=env.gpu_ssh_identity_file,
        connect_timeout=env.gpu_ssh_connect_timeout,
        strict_host_key_checking=env.gpu_ssh_strict_host_key_checking,
    )
    argv = ssh_argv(target, REMOTE_DISCOVERY_SCRIPT.strip())
    proc = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Remote discovery failed (exit {proc.returncode}): {proc.stderr[-2000:]}"
        )
    return json.loads(proc.stdout)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only hardware discovery")
    parser.add_argument(
        "--remote", action="store_true", help="Discover via SSH (requires INFERENCE_ALLOW_REMOTE=1)"
    )
    parser.add_argument("--json", action="store_true", default=True)
    args = parser.parse_args(argv)
    load_local_env()
    try:
        data = discover_remote() if args.remote else discover_local()
    except Exception as exc:  # noqa: BLE001 — CLI boundary
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(redact_mapping(data), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
