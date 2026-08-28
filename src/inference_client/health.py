"""Health and metrics helpers for Phase 1 tests."""

from __future__ import annotations

import httpx


def get_json(
    base_url: str, path: str, *, api_key: str | None = None, tls_verify: bool = True
) -> tuple[int, object]:
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    url = base_url.rstrip("/") + path
    with httpx.Client(timeout=10.0, verify=tls_verify, headers=headers) as client:
        response = client.get(url)
        if response.headers.get("content-type", "").startswith("application/json"):
            return response.status_code, response.json()
        return response.status_code, response.text
