"""Raw HTTPX SSE parser for OpenAI-compatible chat.completions streams.

The OpenAI SDK hides the `data: [DONE]` transport marker. Acceptance tests must
use this parser (or an equivalent transport-level check) rather than the SDK.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

import httpx


@dataclass
class SSEEvent:
    data: str
    event: str | None = None
    id: str | None = None


@dataclass
class SSEStreamResult:
    status: str
    ttft_ms: float | None
    e2e_ms: float
    output_text: str
    chunk_count: int
    event_count: int
    terminal: bool
    saw_done: bool
    finish_reason: str | None
    error: str | None = None
    usage: dict[str, Any] | None = None
    events: list[SSEEvent] = field(default_factory=list)


class SSEParser:
    """Incremental Server-Sent Events parser that accepts fragmented byte chunks."""

    def __init__(self) -> None:
        self._buf = ""

    def feed(self, chunk: bytes | str) -> list[SSEEvent]:
        text = chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
        self._buf += text
        events: list[SSEEvent] = []
        while True:
            sep = _next_separator(self._buf)
            if sep is None:
                break
            raw, self._buf = self._buf.split(sep, 1)
            parsed = _parse_event_block(raw)
            if parsed is not None:
                events.append(parsed)
        return events

    def flush(self) -> list[SSEEvent]:
        if not self._buf.strip():
            self._buf = ""
            return []
        parsed = _parse_event_block(self._buf)
        self._buf = ""
        return [parsed] if parsed is not None else []


def _next_separator(buf: str) -> str | None:
    for sep in ("\r\n\r\n", "\n\n"):
        if sep in buf:
            return sep
    return None


def _parse_event_block(block: str) -> SSEEvent | None:
    data_lines: list[str] = []
    event_name: str | None = None
    event_id: str | None = None
    for line in block.splitlines():
        if not line or line.startswith(":"):
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        elif line.startswith("event:"):
            event_name = line[6:].lstrip()
        elif line.startswith("id:"):
            event_id = line[3:].lstrip()
    if not data_lines and event_name is None:
        return None
    return SSEEvent(data="\n".join(data_lines), event=event_name, id=event_id)


def _content_from_payload(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""
    choice = choices[0]
    delta = choice.get("delta") or {}
    content = delta.get("content")
    if content:
        return str(content)
    message = choice.get("message") or {}
    return str(message.get("content") or "")


def _finish_reason(payload: dict[str, Any]) -> str | None:
    choices = payload.get("choices") or []
    if not choices:
        return None
    return choices[0].get("finish_reason")


def parse_chat_completion_sse(
    chunks: Iterable[bytes | str],
    *,
    time_fn: Callable[[], float] = perf_counter,
) -> SSEStreamResult:
    started = time_fn()
    parser = SSEParser()
    parts: list[str] = []
    ttft_ms: float | None = None
    saw_done = False
    finish_reason: str | None = None
    usage = None
    events: list[SSEEvent] = []
    chunk_count = 0
    malformed = False
    error: str | None = None

    try:
        for chunk in chunks:
            chunk_count += 1
            for event in parser.feed(chunk):
                events.append(event)
                ttft_ms, saw_done, finish_reason, usage, malformed = _fold_event(
                    event,
                    parts=parts,
                    ttft_ms=ttft_ms,
                    started=started,
                    time_fn=time_fn,
                    saw_done=saw_done,
                    finish_reason=finish_reason,
                    usage=usage,
                    malformed=malformed,
                )
        for event in parser.flush():
            events.append(event)
            ttft_ms, saw_done, finish_reason, usage, malformed = _fold_event(
                event,
                parts=parts,
                ttft_ms=ttft_ms,
                started=started,
                time_fn=time_fn,
                saw_done=saw_done,
                finish_reason=finish_reason,
                usage=usage,
                malformed=malformed,
            )
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
        return SSEStreamResult(
            status="error",
            ttft_ms=ttft_ms,
            e2e_ms=(time_fn() - started) * 1000,
            output_text="".join(parts),
            chunk_count=chunk_count,
            event_count=len(events),
            terminal=False,
            saw_done=saw_done,
            finish_reason=finish_reason,
            error=error,
            usage=usage,
            events=events,
        )

    text = "".join(parts)
    e2e_ms = (time_fn() - started) * 1000
    if malformed:
        status = "malformed_json"
    elif error:
        status = "error"
    elif not saw_done:
        status = "missing_done"
    elif not text:
        status = "empty_content"
    elif not finish_reason:
        status = "incomplete"
    else:
        status = "ok"
    return SSEStreamResult(
        status=status,
        ttft_ms=ttft_ms,
        e2e_ms=e2e_ms,
        output_text=text,
        chunk_count=chunk_count,
        event_count=len(events),
        terminal=saw_done and bool(finish_reason),
        saw_done=saw_done,
        finish_reason=finish_reason,
        error=error,
        usage=usage,
        events=events,
    )


def _fold_event(
    event: SSEEvent,
    *,
    parts: list[str],
    ttft_ms: float | None,
    started: float,
    time_fn: Callable[[], float],
    saw_done: bool,
    finish_reason: str | None,
    usage: dict[str, Any] | None,
    malformed: bool,
) -> tuple[float | None, bool, str | None, dict[str, Any] | None, bool]:
    lines = event.data.split("\n") if event.data else [""]
    for line in lines:
        stripped = line.strip()
        if stripped == "[DONE]":
            saw_done = True
            continue
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            malformed = True
            continue
        if not isinstance(payload, dict):
            malformed = True
            continue
        content = _content_from_payload(payload)
        if content:
            if ttft_ms is None:
                ttft_ms = (time_fn() - started) * 1000
            parts.append(content)
        reason = _finish_reason(payload)
        if reason:
            finish_reason = reason
        if payload.get("usage"):
            usage = payload["usage"]
    return ttft_ms, saw_done, finish_reason, usage, malformed


def stream_chat_completion_sse(
    *,
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    api_key: str | None = None,
    timeout: float = 120,
    tls_verify: bool = True,
    transport: httpx.BaseTransport | None = None,
) -> SSEStreamResult:
    """POST /v1/chat/completions and validate the raw SSE transport, including [DONE]."""

    root = base_url.rstrip("/")
    url = root + "/chat/completions" if root.endswith("/v1") else root + "/v1/chat/completions"
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    started = perf_counter()
    client_kwargs: dict[str, Any] = {"timeout": timeout, "verify": tls_verify}
    if transport is not None:
        client_kwargs["transport"] = transport
    try:
        with httpx.Client(**client_kwargs) as client:
            with client.stream("POST", url, json=body, headers=headers) as response:
                if response.status_code != 200:
                    return SSEStreamResult(
                        status="error",
                        ttft_ms=None,
                        e2e_ms=(perf_counter() - started) * 1000,
                        output_text="",
                        chunk_count=0,
                        event_count=0,
                        terminal=False,
                        saw_done=False,
                        finish_reason=None,
                        error=f"HTTP {response.status_code}",
                    )
                return parse_chat_completion_sse(response.iter_bytes())
    except Exception as exc:  # noqa: BLE001
        return SSEStreamResult(
            status="error",
            ttft_ms=None,
            e2e_ms=(perf_counter() - started) * 1000,
            output_text="",
            chunk_count=0,
            event_count=0,
            terminal=False,
            saw_done=False,
            finish_reason=None,
            error=str(exc),
        )
