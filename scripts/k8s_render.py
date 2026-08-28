#!/usr/bin/env python3
"""CLI wrapper for offline Kubernetes manifest rendering."""

from inference_platform.k8s.render import main

if __name__ == "__main__":
    raise SystemExit(main())
