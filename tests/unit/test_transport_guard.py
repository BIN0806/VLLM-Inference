"""Client refuses Bearer tokens on non-loopback HTTP unless a lab override is set."""

from __future__ import annotations

import pytest

from inference_client.client import build_client
from inference_client.health import get_json
from inference_client.sse import stream_chat_completion_sse
from inference_client.transport import (
    InsecureCredentialTransportError,
    InsecureRemoteHttpWarning,
    ensure_safe_credential_transport,
)
from inference_platform.config import EnvSettings, load_profile
from inference_platform.wait import wait_for_service

LOOPBACK_HTTP = "http://127.0.0.1:8000"
LOOPBACK_LOCALHOST = "http://localhost:8000"
REMOTE_HTTP = "http://example.invalid:8000"
REMOTE_HTTPS = "https://example.invalid:8000"
TOKEN = "unit-test-bearer-token"


@pytest.mark.unit
def test_http_loopback_without_credentials_is_allowed() -> None:
    ensure_safe_credential_transport(LOOPBACK_HTTP)
    ensure_safe_credential_transport(LOOPBACK_LOCALHOST, api_key=None)


@pytest.mark.unit
def test_http_loopback_with_credentials_is_allowed() -> None:
    ensure_safe_credential_transport(LOOPBACK_HTTP, api_key=TOKEN)
    ensure_safe_credential_transport(LOOPBACK_LOCALHOST, open_button_token=TOKEN)
    ensure_safe_credential_transport("http://[::1]:8000", api_key=TOKEN)


@pytest.mark.unit
def test_remote_http_without_credentials_is_allowed() -> None:
    """Unauthenticated remote HTTP is a caller choice; this guard only covers secrets."""
    ensure_safe_credential_transport(REMOTE_HTTP)
    ensure_safe_credential_transport(REMOTE_HTTP, api_key=None, open_button_token="")


@pytest.mark.unit
def test_remote_http_with_credentials_is_refused_by_default() -> None:
    with pytest.raises(InsecureCredentialTransportError, match="ALLOW_INSECURE_REMOTE_HTTP"):
        ensure_safe_credential_transport(REMOTE_HTTP, api_key=TOKEN)
    with pytest.raises(InsecureCredentialTransportError):
        ensure_safe_credential_transport(REMOTE_HTTP, open_button_token=TOKEN)
    with pytest.raises(InsecureCredentialTransportError):
        get_json(REMOTE_HTTP, "/v1/models", api_key=TOKEN)
    with pytest.raises(InsecureCredentialTransportError):
        build_client(REMOTE_HTTP, TOKEN)
    with pytest.raises(InsecureCredentialTransportError):
        stream_chat_completion_sse(
            base_url=REMOTE_HTTP,
            model="test-model",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=8,
            api_key=TOKEN,
        )
    with pytest.raises(InsecureCredentialTransportError):
        wait_for_service(REMOTE_HTTP, api_key=TOKEN, timeout_seconds=1)


@pytest.mark.unit
def test_remote_http_with_credentials_and_lab_override_warns() -> None:
    with pytest.warns(InsecureRemoteHttpWarning, match="Lab-only"):
        ensure_safe_credential_transport(
            REMOTE_HTTP,
            api_key=TOKEN,
            allow_insecure_remote_http=True,
        )


@pytest.mark.unit
def test_remote_https_with_credentials_is_allowed() -> None:
    ensure_safe_credential_transport(REMOTE_HTTPS, api_key=TOKEN)
    ensure_safe_credential_transport(REMOTE_HTTPS, open_button_token=TOKEN)


@pytest.mark.unit
def test_placeholder_openai_key_is_not_treated_as_a_secret() -> None:
    ensure_safe_credential_transport(REMOTE_HTTP, api_key="EMPTY")
    build_client(REMOTE_HTTP, None)


@pytest.mark.unit
def test_allow_insecure_remote_http_defaults_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALLOW_INSECURE_REMOTE_HTTP", raising=False)
    env = EnvSettings()
    assert env.allow_insecure_remote_http is False
    public = load_profile("authoring").public_dict()
    assert public["allow_insecure_remote_http"] is False
