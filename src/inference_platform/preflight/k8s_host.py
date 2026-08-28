"""Host-side Phase 3 preflight. Never installs software. Facts can be injected for tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from inference_platform.config import ResolvedConfig
from inference_platform.preflight.results import CheckResult
from inference_platform.topology import HardwareSnapshot, validate_topology


def _host_baseline(config: ResolvedConfig) -> dict[str, Any]:
    return config.pins.get("host_baseline") or {}


def _parse_version(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for token in value.split("."):
        digits = "".join(ch for ch in token if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts) if parts else (0,)


@dataclass
class K8sHostFacts:
    systemd: bool = False
    uid: int | None = None
    disk_total_gib: float | None = None
    disk_free_gib: float | None = None
    ram_gib: float | None = None
    gpu_count: int = 0
    gpu_names: list[str] = field(default_factory=list)
    gpu_vram_mib: list[int] = field(default_factory=list)
    driver_version: str | None = None
    cuda_reported: str | None = None
    containerd: bool = False
    docker: bool = False
    nvidia_container_runtime: bool = False
    kubernetes_available: bool = False
    k3s_active: bool = False
    kubectl_nodes: int | None = None
    nvidia_gpu_allocatable: int | None = None
    source: str = "injected"

    def snapshot(self) -> HardwareSnapshot:
        from inference_platform.topology import GpuDevice

        gpus = [
            GpuDevice(
                index=idx,
                name=self.gpu_names[idx] if idx < len(self.gpu_names) else f"gpu{idx}",
                vram_mib=self.gpu_vram_mib[idx] if idx < len(self.gpu_vram_mib) else 0,
            )
            for idx in range(self.gpu_count)
        ]
        return HardwareSnapshot(
            gpu_count=self.gpu_count,
            gpus=gpus,
            node_count=1,
            driver_version=self.driver_version,
            cuda_reported=self.cuda_reported,
            system_memory_gib=self.ram_gib,
            disk_free_gib=self.disk_free_gib,
            source=self.source,
        )

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> K8sHostFacts:
        return cls(
            systemd=bool(data.get("systemd", False)),
            uid=data.get("uid"),
            disk_total_gib=data.get("disk_total_gib"),
            disk_free_gib=data.get("disk_free_gib"),
            ram_gib=data.get("ram_gib"),
            gpu_count=int(data.get("gpu_count") or 0),
            gpu_names=list(data.get("gpu_names") or []),
            gpu_vram_mib=[int(v) for v in (data.get("gpu_vram_mib") or [])],
            driver_version=data.get("driver_version"),
            cuda_reported=data.get("cuda_reported"),
            containerd=bool(data.get("containerd", False)),
            docker=bool(data.get("docker", False)),
            nvidia_container_runtime=bool(data.get("nvidia_container_runtime", False)),
            kubernetes_available=bool(data.get("kubernetes_available", False)),
            k3s_active=bool(data.get("k3s_active", False)),
            kubectl_nodes=data.get("kubectl_nodes"),
            nvidia_gpu_allocatable=data.get("nvidia_gpu_allocatable"),
            source=str(data.get("source", "mapping")),
        )


def evaluate_k8s_host(
    config: ResolvedConfig,
    facts: K8sHostFacts,
    *,
    require_cluster: bool = True,
) -> list[CheckResult]:
    """Fail closed against the selected model. Never changes model or TP."""

    results: list[CheckResult] = []
    baseline = _host_baseline(config)
    min_disk = float(baseline.get("min_disk_gib", 80))
    pref_disk = float(baseline.get("preferred_disk_gib", 100))
    min_ram = float(baseline.get("min_ram_gib", 16))
    pref_ram = float(baseline.get("preferred_ram_gib", 32))
    min_driver = str(baseline.get("min_nvidia_driver", "550.0.0"))

    if facts.systemd:
        results.append(CheckResult("systemd", "PASS", "systemd is present"))
    else:
        results.append(
            CheckResult(
                "systemd",
                "FAIL",
                "systemd is not available",
                remediation="Rent a VM-capable Linux image (not a Jupyter/container template).",
            )
        )

    if facts.uid == 0:
        results.append(CheckResult("root", "PASS", "Running as root"))
    else:
        results.append(
            CheckResult(
                "root",
                "FAIL",
                f"uid={facts.uid} is not root",
                remediation="Phase 3 host setup expects root on the rental VM.",
            )
        )

    disk_total = facts.disk_total_gib
    if disk_total is None:
        results.append(CheckResult("disk", "FAIL", "Host disk size was not reported"))
    elif disk_total < min_disk:
        results.append(
            CheckResult(
                "disk",
                "FAIL",
                f"{disk_total:.1f} GiB disk is below the {min_disk:.0f} GiB Phase 3 floor",
                remediation="Select an offer with at least 80 GiB disk, preferably 100 GiB.",
                details={"disk_total_gib": disk_total, "disk_free_gib": facts.disk_free_gib},
            )
        )
    elif disk_total < pref_disk:
        results.append(
            CheckResult(
                "disk",
                "WARN",
                f"{disk_total:.1f} GiB disk meets the floor but is below the {pref_disk:.0f} GiB preference",
                details={"disk_total_gib": disk_total, "disk_free_gib": facts.disk_free_gib},
            )
        )
    else:
        results.append(
            CheckResult(
                "disk",
                "PASS",
                f"{disk_total:.1f} GiB disk",
                details={"disk_total_gib": disk_total, "disk_free_gib": facts.disk_free_gib},
            )
        )

    ram = facts.ram_gib
    if ram is None:
        results.append(CheckResult("ram", "FAIL", "Host RAM was not reported"))
    elif ram < min_ram:
        results.append(
            CheckResult(
                "ram",
                "FAIL",
                f"{ram:.1f} GiB RAM is below the {min_ram:.0f} GiB floor",
                remediation="Need RAM for k3s plus vLLM; 32 GiB is preferred.",
            )
        )
    elif ram < pref_ram:
        results.append(
            CheckResult(
                "ram",
                "WARN",
                f"{ram:.1f} GiB RAM meets the floor; {pref_ram:.0f} GiB is preferred",
            )
        )
    else:
        results.append(CheckResult("ram", "PASS", f"{ram:.1f} GiB RAM"))

    if facts.gpu_count < 1:
        results.append(CheckResult("gpu-inventory", "FAIL", "No NVIDIA GPUs discovered"))
    else:
        results.append(
            CheckResult(
                "gpu-inventory",
                "PASS",
                f"{facts.gpu_count} GPU(s): {', '.join(facts.gpu_names) or 'name-unknown'}",
                details={"vram_mib": facts.gpu_vram_mib, "names": facts.gpu_names},
            )
        )

    if not facts.driver_version:
        results.append(
            CheckResult(
                "driver",
                "FAIL",
                "NVIDIA driver version was not reported",
                remediation="Install a driver that can run the pinned vLLM CUDA image.",
            )
        )
    elif _parse_version(facts.driver_version) < _parse_version(min_driver):
        results.append(
            CheckResult(
                "driver",
                "FAIL",
                f"Driver {facts.driver_version} is older than minimum {min_driver}",
                details={"driver": facts.driver_version, "cuda": facts.cuda_reported},
            )
        )
    else:
        results.append(
            CheckResult(
                "driver",
                "PASS",
                f"Driver {facts.driver_version}",
                details={"driver": facts.driver_version, "cuda": facts.cuda_reported},
            )
        )

    if facts.containerd or facts.docker:
        runtime = "containerd" if facts.containerd else "docker"
        results.append(CheckResult("container-runtime", "PASS", f"{runtime} is present"))
    else:
        results.append(
            CheckResult(
                "container-runtime",
                "FAIL",
                "Neither containerd nor Docker is present",
                remediation="See docs/runbooks/k3s-nvidia.md. Do not install from this repository yet.",
            )
        )

    if require_cluster:
        if facts.kubernetes_available or facts.k3s_active or (facts.kubectl_nodes or 0) >= 1:
            results.append(
                CheckResult(
                    "kubernetes",
                    "PASS",
                    "Kubernetes API is reachable",
                    details={"k3s_active": facts.k3s_active, "kubectl_nodes": facts.kubectl_nodes},
                )
            )
        else:
            results.append(
                CheckResult(
                    "kubernetes",
                    "FAIL",
                    "Kubernetes is not available on this host",
                    remediation="Install k3s per docs/runbooks/k3s-nvidia.md after the rental exists. Do not run that install from this repo until approved.",
                )
            )
        if facts.nvidia_container_runtime:
            results.append(
                CheckResult("nvidia-runtime", "PASS", "NVIDIA container runtime is present")
            )
        else:
            results.append(
                CheckResult(
                    "nvidia-runtime",
                    "FAIL",
                    "NVIDIA container runtime is not configured",
                    remediation="Install NVIDIA Container Toolkit per docs/runbooks/k3s-nvidia.md after approval.",
                )
            )
        if facts.nvidia_gpu_allocatable is None:
            results.append(
                CheckResult(
                    "nvidia.com/gpu",
                    "WARN",
                    "nvidia.com/gpu allocatable count is unknown",
                    remediation="After the device plugin is installed, confirm kubectl describe node shows nvidia.com/gpu: 1.",
                )
            )
        elif facts.nvidia_gpu_allocatable < 1:
            results.append(
                CheckResult(
                    "nvidia.com/gpu",
                    "FAIL",
                    "Node does not advertise nvidia.com/gpu",
                    remediation="Install NVIDIA device plugin 0.20.0. Do not hide it inside the app Deployment.",
                )
            )
        else:
            results.append(
                CheckResult(
                    "nvidia.com/gpu",
                    "PASS",
                    f"Node allocatable nvidia.com/gpu={facts.nvidia_gpu_allocatable}",
                )
            )
    else:
        results.append(
            CheckResult(
                "kubernetes",
                "SKIP",
                "Cluster checks skipped (--require-cluster not set)",
            )
        )
        results.append(
            CheckResult(
                "nvidia-runtime",
                "SKIP",
                "NVIDIA runtime checks skipped (--require-cluster not set)",
            )
        )

    topology = validate_topology(config, facts.snapshot())
    fails = [issue.message for issue in topology.issues if issue.severity == "FAIL"]
    if fails:
        results.append(
            CheckResult(
                "model-fit",
                "FAIL",
                fails[0],
                remediation="Keep the selected model. Do not silently switch to 1.5B or change TP. Pick another SKU or another explicit profile.",
                details={"issues": [issue.__dict__ for issue in topology.issues]},
            )
        )
    else:
        warn = [issue.message for issue in topology.issues if issue.severity == "WARN"]
        results.append(
            CheckResult(
                "model-fit",
                "WARN" if warn else "PASS",
                warn[0]
                if warn
                else f"{config.model_id} fits discovered GPUs at TP={config.tensor_parallel_size}",
                details={"issues": [issue.__dict__ for issue in topology.issues]},
            )
        )
    return results
