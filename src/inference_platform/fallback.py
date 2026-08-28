"""Explicit, never-silent fallbacks. A fallback cannot pass the originally requested gate."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from inference_platform.config import ModelConfig, ResolvedConfig
from inference_platform.topology import TopologyReport


@dataclass
class FallbackEvent:
    kind: str
    requested: str
    actual: str
    reason: str
    enabled_by: str
    originally_requested_gate: str = "cannot-pass"


def maybe_tp_fallback(
    config: ResolvedConfig,
    topology: TopologyReport,
) -> tuple[int, FallbackEvent | None]:
    requested = config.tensor_parallel_size
    if topology.ok or requested <= 1:
        return requested, None
    tp_issue = any(issue.code == "tp-exceeds-gpus" for issue in topology.issues)
    if not tp_issue:
        return requested, None
    if not config.env.allow_tp_fallback:
        return requested, None
    visible = topology.gpus_visible or 1
    actual = min(requested, visible, 1) if visible < requested else requested
    if actual == requested:
        return requested, None
    event = FallbackEvent(
        kind="tensor-parallel",
        requested=str(requested),
        actual=str(actual),
        reason="Visible GPU count is insufficient for the requested tensor parallel size",
        enabled_by="ALLOW_TP_FALLBACK",
    )
    return actual, event


def maybe_model_fallback(
    config: ResolvedConfig,
    topology: TopologyReport,
) -> tuple[ModelConfig, FallbackEvent | None]:
    fit_fail = any(issue.code == "model-does-not-fit" for issue in topology.issues)
    if not fit_fail:
        return config.model, None
    if not config.env.allow_model_fallback:
        return config.model, None
    if config.fallback_model is None:
        return config.model, None
    event = FallbackEvent(
        kind="model",
        requested=config.model.model_id,
        actual=config.fallback_model.model_id,
        reason="Requested model cannot fit available per-rank VRAM",
        enabled_by="ALLOW_MODEL_FALLBACK",
    )
    return config.fallback_model, event


def format_fallback_banner(event: FallbackEvent) -> str:
    return (
        "FALLBACK USED — originally requested hardware gate CANNOT PASS\n"
        f"  kind: {event.kind}\n"
        f"  requested: {event.requested}\n"
        f"  actual: {event.actual}\n"
        f"  reason: {event.reason}\n"
        f"  enabled_by: {event.enabled_by}\n"
    )


def event_dict(event: FallbackEvent) -> dict[str, str]:
    return asdict(event)
