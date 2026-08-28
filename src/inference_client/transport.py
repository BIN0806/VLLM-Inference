"""Refuse sending Bearer credentials over non-loopback HTTP unless explicitly overridden."""

from __future__ import annotations

import ipaddress
import warnings
from urllib.parse import urlsplit

_PLACEHOLDER_KEYS = frozenset({"", "EMPTY", "empty"})
_LOOPBACK_NAMES = frozenset({"localhost", "localhost.", "ip6-localhost", "ip6-loopback"})

INSECURE_REMOTE_HTTP_WARNING = (
    "ALLOW_INSECURE_REMOTE_HTTP is enabled: sending a Bearer token to a "
    "non-loopback http:// URL. Authentication does not provide confidentiality. "
    "On-path observers can read the token and the request body. Lab-only; "
    "never enable this for production. Prefer an SSH tunnel to loopback or HTTPS."
)


class InsecureRemoteHttpWarning(UserWarning):
    """Emitted only when ALLOW_INSECURE_REMOTE_HTTP explicitly overrides the guard."""


class InsecureCredentialTransportError(ValueError):
    """Credentials would be sent over plaintext HTTP to a non-loopback host."""


def _has_credential(*values: str | None) -> bool:
    for value in values:
        if value is None:
            continue
        if value.strip() and value.strip() not in _PLACEHOLDER_KEYS:
            return True
    return False


def is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    normalized = host.strip().rstrip(".").lower()
    if normalized in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def ensure_safe_credential_transport(
    url: str,
    *,
    api_key: str | None = None,
    open_button_token: str | None = None,
    allow_insecure_remote_http: bool = False,
) -> None:
    """Raise unless credentials are omitted, the URL is HTTPS, or the host is loopback HTTP.

    SSH tunnels to 127.0.0.1/localhost may send Bearer tokens over HTTP.
    Non-loopback http:// URLs require ALLOW_INSECURE_REMOTE_HTTP (lab-only).
    Unauthenticated requests are not blocked here; callers decide that separately.
    """

    if not _has_credential(api_key, open_button_token):
        return

    parts = urlsplit(url)
    scheme = (parts.scheme or "").lower()
    host = parts.hostname
    if scheme == "https":
        return
    if scheme == "http" and is_loopback_host(host):
        return
    if scheme == "http" and allow_insecure_remote_http:
        warnings.warn(INSECURE_REMOTE_HTTP_WARNING, InsecureRemoteHttpWarning, stacklevel=2)
        return
    raise InsecureCredentialTransportError(
        "Refusing to send VLLM_API_KEY or OPEN_BUTTON_TOKEN to a non-loopback "
        "http:// URL. Bearer authentication without TLS does not protect the "
        "token or the prompt. Use an SSH tunnel to loopback or properly "
        "configured HTTPS. Lab-only override: ALLOW_INSECURE_REMOTE_HTTP=true "
        f"(got scheme={scheme!r} host={host!r})."
    )
