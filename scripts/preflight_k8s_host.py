#!/usr/bin/env python3
"""CLI wrapper for Kubernetes host preflight."""

from inference_platform.preflight.k8s_host_cli import main

if __name__ == "__main__":
    raise SystemExit(main())
