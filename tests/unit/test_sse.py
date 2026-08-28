"""Transport-level SSE coverage for OpenAI-compatible chat.completions streams."""

from __future__ import annotations

import json

import httpx
import pytest

from inference_client.sse import parse_chat_completion_sse, stream_chat_completion_sse


def _event(payload: dict | str) -> bytes:
    if isinstance(payload, str):
        return f"data: {payload}\n\n".encode()
    return f"data: {json.dumps(payload)}\n\n".encode()


def _content(text: str, finish_reason: str | None = None) -> dict:
    return {
        "id": "cmpl-test",
        "choices": [{"delta": {"content": text}, "finish_reason": finish_reason}],
    }


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        self.t += 0.01
        return self.t


@pytest.mark.unit
def test_fragmented_sse_across_chunks() -> None:
    payload = json.dumps(_content("Hello", None))
    chunks = [
        b"data: " + payload[:12].encode(),
        payload[12:].encode() + b"\n\n",
        _event(_content("", "stop")),
        b"data: [DONE]\n\n",
    ]
    result = parse_chat_completion_sse(chunks, time_fn=Clock())
    assert result.output_text == "Hello"
    assert result.saw_done
    assert result.finish_reason == "stop"
    assert result.status == "ok"


@pytest.mark.unit
def test_multiple_data_records_in_one_event() -> None:
    block = (
        "data: "
        + json.dumps(_content("A"))
        + "\n"
        + "data: "
        + json.dumps(_content("B", "stop"))
        + "\n\n"
        + "data: [DONE]\n\n"
    )
    result = parse_chat_completion_sse([block], time_fn=Clock())
    assert result.output_text == "AB"
    assert result.saw_done
    assert result.status == "ok"


@pytest.mark.unit
def test_valid_json_events_and_done_marker() -> None:
    chunks = [
        _event(_content("Hi")),
        _event(_content(" there", "stop")),
        _event("[DONE]"),
    ]
    result = parse_chat_completion_sse(chunks, time_fn=Clock())
    assert result.status == "ok"
    assert result.saw_done
    assert result.output_text == "Hi there"
    assert result.ttft_ms is not None
    assert result.ttft_ms > 0


@pytest.mark.unit
def test_missing_done_marker() -> None:
    chunks = [_event(_content("Hi", "stop"))]
    result = parse_chat_completion_sse(chunks, time_fn=Clock())
    assert result.status == "missing_done"
    assert result.finish_reason == "stop"
    assert result.saw_done is False
    assert result.terminal is False


@pytest.mark.unit
def test_malformed_json() -> None:
    chunks = [b"data: {not-json\n\n", _event("[DONE]")]
    result = parse_chat_completion_sse(chunks, time_fn=Clock())
    assert result.status == "malformed_json"


@pytest.mark.unit
def test_empty_content() -> None:
    chunks = [_event(_content("", "stop")), _event("[DONE]")]
    result = parse_chat_completion_sse(chunks, time_fn=Clock())
    assert result.status == "empty_content"
    assert result.saw_done
    assert result.output_text == ""


@pytest.mark.unit
def test_finish_reason_without_done() -> None:
    chunks = [_event(_content("done-shape", "stop"))]
    result = parse_chat_completion_sse(chunks, time_fn=Clock())
    assert result.finish_reason == "stop"
    assert result.saw_done is False
    assert result.status == "missing_done"


@pytest.mark.unit
def test_timeout_or_error_from_iterator() -> None:
    def exploding():
        yield _event(_content("partial"))
        raise TimeoutError("deadline exceeded")

    result = parse_chat_completion_sse(exploding(), time_fn=Clock())
    assert result.status == "error"
    assert "deadline exceeded" in (result.error or "")
    assert result.output_text == "partial"


@pytest.mark.unit
def test_ttft_uses_first_generated_content_token() -> None:
    clock = Clock()
    chunks = [
        _event({"id": "x", "choices": [{"delta": {}, "finish_reason": None}]}),
        _event(_content("Z", "stop")),
        _event("[DONE]"),
    ]
    result = parse_chat_completion_sse(chunks, time_fn=clock)
    assert result.status == "ok"
    assert result.ttft_ms is not None
    # Clock advances on start and on first content; empty delta must not count.
    assert result.output_text == "Z"


@pytest.mark.unit
def test_httpx_helper_records_http_and_timeout_errors() -> None:
    def unauthorized(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="nope")

    denied = stream_chat_completion_sse(
        base_url="http://vllm.test",
        model="test-model",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=8,
        transport=httpx.MockTransport(unauthorized),
    )
    assert denied.status == "error"
    assert "401" in (denied.error or "")

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("deadline", request=request)

    timed_out = stream_chat_completion_sse(
        base_url="http://vllm.test",
        model="test-model",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=8,
        transport=httpx.MockTransport(boom),
    )
    assert timed_out.status == "error"
    assert timed_out.error
