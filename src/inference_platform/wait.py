"""Bounded wait for an OpenAI-compatible vLLM endpoint. Ready means HTTP 200 only."""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin

import httpx

from inference_platform.config import EnvSettings, load_local_env

SleepFn = Callable[[float], None]


def wait_for_service(
    base_url: str,
    *,
    timeout_seconds: float = 180,
    interval_seconds: float = 2,
    api_key: str | None = None,
    tls_verify: bool = True,
    health_path: str = "/health",
    transport: httpx.BaseTransport | None = None,
    sleep: SleepFn = time.sleep,
    request_timeout: float = 5.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    url = urljoin(base_url.rstrip("/") + "/", health_path.lstrip("/"))
    last_error = "no attempts"
    attempts = 0
    while time.monotonic() < deadline:
        attempts += 1
        try:
            client_kwargs: dict[str, Any] = {
                "timeout": request_timeout,
                "verify": tls_verify,
                "headers": headers,
            }
            if transport is not None:
                client_kwargs["transport"] = transport
            with httpx.Client(**client_kwargs) as client:
                response = client.get(url)
            if response.status_code == 200:
                return
            last_error = f"HTTP {response.status_code} from {url}"
        except httpx.HTTPError as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        sleep(min(interval_seconds, remaining))
    raise TimeoutError(
        f"Service at {url} not ready within {timeout_seconds}s after {attempts} attempt(s); "
        f"last_error={last_error}"
    )


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
