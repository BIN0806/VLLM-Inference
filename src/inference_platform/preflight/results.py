"""Preflight check result types."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

Status = Literal["PASS", "WARN", "SKIP", "FAIL"]


@dataclass
class CheckResult:
    name: str
    status: Status
    summary: str
    remediation: str | None = None
    details: dict | None = None

    def as_dict(self) -> dict:
        payload = asdict(self)
        return payload
