"""Query Prometheus HTTP API over SSH-tunneled loopback."""

from __future__ import annotations

from urllib.parse import urlsplit

import httpx

from inference_client.transport import ensure_safe_credential_transport, is_loopback_host


class PrometheusQueryError(ValueError):
    """Prometheus must be reached on loopback, typically via an SSH tunnel."""


def instant_query(
    base_url: str,
    query: str,
    *,
    tls_verify: bool = True,
    allow_insecure_remote_http: bool = False,
    timeout: float = 15.0,
) -> dict:
    url = base_url.rstrip("/") + "/api/v1/query"
    host = urlsplit(base_url).hostname
    if not is_loopback_host(host):
        raise PrometheusQueryError(
            "Prometheus queries must use SSH-tunneled loopback "
            "(PROMETHEUS_BASE_URL on 127.0.0.1/localhost). "
            "Do not scrape or query a public Prometheus URL."
        )
    ensure_safe_credential_transport(
        url,
        api_key=None,
        allow_insecure_remote_http=allow_insecure_remote_http,
    )
    with httpx.Client(timeout=timeout, verify=tls_verify) as client:
        response = client.get(url, params={"query": query})
        response.raise_for_status()
        payload = response.json()
    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus query failed: {payload}")
    return payload
