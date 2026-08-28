"""Record the concurrency that actually ran. Never silently cap without saying so."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConcurrencyPlan:
    requested: int
    effective: int
    capped: bool
    cap: int | None


def plan_concurrency(requested: int, cap: int | None = None) -> ConcurrencyPlan:
    if requested < 1:
        raise ValueError("concurrency must be >= 1")
    if cap is None or cap <= 0 or requested <= cap:
        return ConcurrencyPlan(requested=requested, effective=requested, capped=False, cap=cap)
    return ConcurrencyPlan(requested=requested, effective=cap, capped=True, cap=cap)
