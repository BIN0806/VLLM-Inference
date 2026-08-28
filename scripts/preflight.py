#!/usr/bin/env python3
"""CLI wrapper for `python -m inference_platform.preflight`."""

from inference_platform.preflight.runner import main

if __name__ == "__main__":
    raise SystemExit(main())
