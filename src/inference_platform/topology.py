"""Validate requested serving topology against discovered hardware. Fail-fast by default."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from inference_platform.config import ModelConfig, ResolvedConfig

Severity = Literal["FAIL", "WARN", "PASS"]


@dataclass
class TopologyIssue:
    severity: Severity
    code: str
    message: str


@dataclass
class TopologyReport:
    ok: bool
    issues: list[TopologyIssue] = field(default_factory=list)
    gpus_required: int | None = None
    gpus_visible: int | None = None
    estimated_weight_gib_per_rank: float | None = None

    def add(self, severity: Severity, code: str, message: str) -> None:
        self.issues.append(TopologyIssue(severity, code, message))
        if severity == "FAIL":
            self.ok = False


@dataclass
class GpuDevice:
    index: int
    name: str
    vram_mib: int
    free_vram_mib: int | None = None


@dataclass
class HardwareSnapshot:
    gpu_count: int
    gpus: list[GpuDevice] = field(default_factory=list)
    node_count: int = 1
    driver_version: str | None = None
    cuda_reported: str | None = None
    system_memory_gib: float | None = None
    disk_free_gib: float | None = None
    shm_gib: float | None = None
    interconnect: str | None = None
    source: str = "unknown"

    @property
    def names(self) -> list[str]:
        return [gpu.name for gpu in self.gpus]

    @property
    def vram_mib_values(self) -> list[int]:
        return [gpu.vram_mib for gpu in self.gpus]

    def min_vram_gib(self) -> float | None:
        if not self.gpus:
            return None
        return min(gpu.vram_mib for gpu in self.gpus) / 1024.0


def gpus_required_for_replica(config: ResolvedConfig) -> int:
    compute = config.compute
    if compute is None:
        return config.tensor_parallel_size * config.pipeline_parallel_size
    if compute.id == "multi-gpu-replicas":
        return compute.replica_count * compute.gpus_per_replica
    return config.tensor_parallel_size * config.pipeline_parallel_size


def estimate_weight_per_rank_gib(model: ModelConfig, tensor_parallel_size: int) -> float:
    return model.weight_gib / max(tensor_parallel_size, 1)


def validate_topology(
    config: ResolvedConfig,
    hardware: HardwareSnapshot | None,
    *,
    requested_model: ModelConfig | None = None,
) -> TopologyReport:
    report = TopologyReport(ok=True)
    model = requested_model or config.model
    tp = config.tensor_parallel_size
    pp = config.pipeline_parallel_size
    backend = config.distributed_executor_backend
    required = gpus_required_for_replica(config)
    report.gpus_required = required
    report.estimated_weight_gib_per_rank = estimate_weight_per_rank_gib(model, tp)

    if tp < 1 or pp < 1:
        report.add(
            "FAIL",
            "invalid-parallelism",
            "tensor_parallel_size and pipeline_parallel_size must be >= 1",
        )
    if config.serving.trust_remote_code or model.trust_remote_code:
        report.add(
            "FAIL",
            "trust-remote-code",
            "trust_remote_code is false by policy unless an ADR records a proven requirement",
        )
    if backend not in {"mp", "ray"}:
        report.add("FAIL", "executor-backend", f"Unknown distributed executor backend {backend!r}")

    compute = config.compute
    if compute is not None and compute.id == "ray-multinode" and compute.requires_nodes >= 2:
        if hardware is None or hardware.node_count < 2:
            report.add(
                "FAIL",
                "multinode-unavailable",
                "ray-multinode requires at least two independently scheduled GPU machines. "
                "Status: NOT RUN — HARDWARE UNAVAILABLE",
            )
    if compute is not None and compute.id == "single-gpu" and tp != 1:
        report.add(
            "FAIL",
            "single-gpu-tp",
            f"single-gpu compute profile requires tensor_parallel_size=1, requested {tp}",
        )
    if compute is not None and compute.id in {"k8s-replica", "k8s-replicas", "k8s-replica-zero"}:
        if tp != 1 or pp != 1:
            report.add(
                "FAIL",
                "k8s-parallelism",
                "k8s-replica requires TP=1 and PP=1; do not change topology silently",
            )
        if backend != "mp":
            report.add(
                "FAIL",
                "k8s-no-ray",
                "k8s-replica uses the mp executor; Ray/KubeRay is a later gate",
            )
        if compute.gpus_per_replica != 1:
            report.add(
                "FAIL",
                "k8s-gpu-count",
                "k8s-replica first gate requests nvidia.com/gpu: 1",
            )
    if compute is not None and compute.id == "multi-gpu-replicas" and tp != 1:
        report.add(
            "FAIL",
            "replica-tp-mix",
            "multi-gpu-replicas uses independent replicas with TP=1; use multi-gpu-tp to shard one replica",
        )

    if hardware is None:
        report.add(
            "WARN",
            "hardware-unknown",
            "No hardware snapshot supplied; GPU-count and VRAM checks were not executed",
        )
        return report

    report.gpus_visible = hardware.gpu_count
    if hardware.gpu_count < 1:
        report.add("FAIL", "no-gpu", "No NVIDIA GPUs visible on the target host")
        return report
    if tp > hardware.gpu_count:
        report.add(
            "FAIL",
            "tp-exceeds-gpus",
            f"tensor_parallel_size={tp} exceeds visible GPU count {hardware.gpu_count}",
        )
    if required > hardware.gpu_count:
        report.add(
            "FAIL",
            "insufficient-gpus",
            f"Topology needs {required} GPU(s) for a complete replica; {hardware.gpu_count} visible",
        )

    names = {gpu.name for gpu in hardware.gpus}
    vrams = {gpu.vram_mib for gpu in hardware.gpus}
    if len(names) > 1 or len(vrams) > 1:
        report.add(
            "WARN",
            "heterogeneous-gpus",
            f"Heterogeneous GPUs detected: names={sorted(names)} vram_mib={sorted(vrams)}",
        )

    min_vram = hardware.min_vram_gib()
    if min_vram is not None:
        per_rank = estimate_weight_per_rank_gib(model, tp)
        if per_rank > min_vram * 0.95:
            report.add(
                "FAIL",
                "model-does-not-fit",
                f"Estimated weights {per_rank:.1f} GiB/rank exceed ~95% of minimum GPU VRAM "
                f"{min_vram:.1f} GiB for {model.model_id}",
            )
        elif model.estimated_min_vram_gib / max(tp, 1) > min_vram:
            report.add(
                "FAIL" if compute is not None and compute.id.startswith("k8s-") else "WARN",
                "vram-below-model-floor",
                f"{model.model_id} estimated_min_vram_gib={model.estimated_min_vram_gib} exceeds "
                f"visible GPU VRAM {min_vram:.1f} GiB; refusing to change the model or topology",
            )
        elif model.estimated_min_vram_gib / max(tp, 1) > min_vram * 0.85:
            report.add(
                "WARN",
                "tight-vram",
                f"{model.model_id} estimated_min_vram_gib={model.estimated_min_vram_gib} on "
                f"{min_vram:.1f} GiB GPU may leave little KV-cache headroom "
                f"(max_model_len={config.max_model_len}, max_num_seqs={config.max_num_seqs})",
            )

    if hardware.disk_free_gib is not None and model.used_storage_gib:
        if hardware.disk_free_gib < model.used_storage_gib + 2:
            report.add(
                "WARN",
                "disk-tight",
                f"Free disk {hardware.disk_free_gib:.1f} GiB may be insufficient for "
                f"{model.used_storage_gib:.1f} GiB model snapshot plus runtime files",
            )
    return report


def snapshot_from_mapping(data: dict[str, Any]) -> HardwareSnapshot:
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
        source=str(data.get("source", "mapping")),
    )
