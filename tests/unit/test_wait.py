"""Health readiness is HTTP 200 only."""

from __future__ import annotations

import httpx
import pytest

from inference_platform.wait import wait_for_service


def _transport(status: int) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=f"status-{status}")

    return httpx.MockTransport(handler)


@pytest.mark.unit
def test_http_200_is_ready() -> None:
    wait_for_service(
        "http://vllm.test",
        timeout_seconds=1,
        interval_seconds=0,
        transport=_transport(200),
    )


@pytest.mark.unit
@pytest.mark.parametrize("status", [301, 401, 404, 500])
def test_non_200_is_not_ready(status: int) -> None:
    with pytest.raises(TimeoutError, match=rf"HTTP {status}"):
        wait_for_service(
            "http://vllm.test",
            timeout_seconds=0.05,
            interval_seconds=0.01,
            transport=_transport(status),
            sleep=lambda _s: None,
        )


@pytest.mark.unit
def test_connection_failure_is_not_ready() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(TimeoutError, match="ConnectError"):
        wait_for_service(
            "http://vllm.test",
            timeout_seconds=0.05,
            interval_seconds=0.01,
            transport=httpx.MockTransport(handler),
            sleep=lambda _s: None,
        )


@pytest.mark.unit
def test_timeout_includes_last_error_and_url() -> None:
    with pytest.raises(TimeoutError, match="http://vllm.test/health") as exc:
        wait_for_service(
            "http://vllm.test",
            timeout_seconds=0.02,
            interval_seconds=0.01,
            transport=_transport(401),
            sleep=lambda _s: None,
        )
    assert "last_error=HTTP 401" in str(exc.value)
    assert "attempt" in str(exc.value)
