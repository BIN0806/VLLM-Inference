#!/usr/bin/env python3
"""Download a pinned model revision into a versioned directory. Inference-only."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Download a pinned Hugging Face revision")
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if os.environ.get("INFERENCE_ALLOW_REMOTE") != "1" and Path(args.output).is_absolute():
        if str(args.output).startswith("/workspace"):
            print("Refusing remote cache paths until INFERENCE_ALLOW_REMOTE=1", file=sys.stderr)
            return 2
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("huggingface_hub is not installed in the authoring environment.", file=sys.stderr)
        print(
            "Install it on the GPU host or add it when actually downloading weights.",
            file=sys.stderr,
        )
        return 1
    dest = Path(args.output) / args.revision
    dest.parent.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=args.model_id,
        revision=args.revision,
        local_dir=str(dest),
    )
    marker = dest / ".download-complete"
    marker.write_text(f"{args.model_id}@{args.revision}\n", encoding="utf-8")
    print(dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
