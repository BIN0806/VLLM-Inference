"""Health and metrics helpers for Phase 1 tests."""

from __future__ import annotations

import httpx

from inference_client.transport import ensure_safe_credential_transport


def get_json(
    base_url: str,
    path: str,
    *,
    api_key: str | None = None,
    tls_verify: bool = True,
    allow_insecure_remote_http: bool = False,
) -> tuple[int, object]:
    url = base_url.rstrip("/") + path
    ensure_safe_credential_transport(
        url,
        api_key=api_key,
        allow_insecure_remote_http=allow_insecure_remote_http,
    )
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    with httpx.Client(timeout=10.0, verify=tls_verify, headers=headers) as client:
        response = client.get(url)
        if response.headers.get("content-type", "").startswith("application/json"):
            return response.status_code, response.json()
        return response.status_code, response.text
