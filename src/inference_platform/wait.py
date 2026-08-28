"""Bounded wait for an OpenAI-compatible vLLM endpoint."""

from __future__ import annotations

import argparse
import sys
import time
from urllib.parse import urljoin

import httpx

from inference_platform.config import EnvSettings, load_local_env


def wait_for_service(
    base_url: str,
    *,
    timeout_seconds: float = 180,
    interval_seconds: float = 2,
    api_key: str | None = None,
    tls_verify: bool = True,
    health_path: str = "/health",
) -> None:
    deadline = time.monotonic() + timeout_seconds
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    url = urljoin(base_url.rstrip("/") + "/", health_path.lstrip("/"))
    last_error = "no attempts"
    while time.monotonic() < deadline:
        try:
            with httpx.Client(timeout=5.0, verify=tls_verify, headers=headers) as client:
                response = client.get(url)
            if response.status_code < 500:
                return
            last_error = f"HTTP {response.status_code}"
        except httpx.HTTPError as exc:
            last_error = str(exc)
        time.sleep(interval_seconds)
    raise TimeoutError(f"Service at {base_url} not ready within {timeout_seconds}s ({last_error})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wait for vLLM health endpoint")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args(argv)
    load_local_env()
    env = EnvSettings()
    base_url = args.base_url or env.vllm_base_url
    try:
        wait_for_service(
            base_url,
            timeout_seconds=args.timeout,
            api_key=env.vllm_api_key,
            tls_verify=env.vllm_tls_verify,
        )
    except TimeoutError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"ready: {base_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
