#!/usr/bin/env python3
"""Collect non-secret local diagnostics."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from inference_platform.config import load_profile
from inference_platform.hardware import discover_local
from inference_platform.paths import artifacts_dir
from inference_platform.secrets import redact_mapping


def main() -> int:
    profile = load_profile("authoring")
    payload = redact_mapping(
        {
            "generated_at": datetime.now(UTC).isoformat(),
            "config": profile.public_dict(),
            "local_hardware": discover_local(),
        }
    )
    path = artifacts_dir() / "diagnostics-local.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
