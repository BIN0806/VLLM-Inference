"""OpenAI-compatible streaming client for vLLM. Auth is optional for tunnels."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

import httpx
from openai import OpenAI


@dataclass
class StreamResult:
    status: str
    ttft_ms: float | None
    e2e_ms: float
    output_text: str
    chunk_count: int
    terminal: bool
    error: str | None = None
    usage: dict[str, Any] | None = None
    raw_events: list[str] = field(default_factory=list)


def build_client(
    base_url: str,
    api_key: str | None,
    *,
    timeout: float = 120,
    tls_verify: bool = True,
) -> OpenAI:
    key = api_key if api_key else "EMPTY"
    http_client = httpx.Client(verify=tls_verify, timeout=timeout)
    return OpenAI(
        base_url=base_url.rstrip("/") + "/v1"
        if not base_url.rstrip("/").endswith("/v1")
        else base_url,
        api_key=key,
        timeout=timeout,
        http_client=http_client,
    )


def list_models(client: OpenAI) -> list[str]:
    page = client.models.list()
    return [item.id for item in page.data]


def resolve_model_id(available: list[str], *, served_name: str, model_id: str) -> str:
    """Use the live served alias when present; otherwise the Hugging Face model id."""
    if served_name in available:
        return served_name
    if model_id in available:
        return model_id
    raise RuntimeError(
        "Live /v1/models returned neither the configured served name nor the model id: "
        f"served={served_name!r} model_id={model_id!r} available={available!r}"
    )


def stream_chat_completion(
    client: OpenAI,
    *,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    timeout: float = 120,
) -> StreamResult:
    started = perf_counter()
    ttft_ms: float | None = None
    parts: list[str] = []
    chunk_count = 0
    terminal = False
    usage = None
    try:
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            stream=True,
            stream_options={"include_usage": True},
            timeout=timeout,
        )
        for chunk in stream:
            chunk_count += 1
            choice = chunk.choices[0] if chunk.choices else None
            if choice is not None and choice.delta and choice.delta.content:
                if ttft_ms is None:
                    ttft_ms = (perf_counter() - started) * 1000
                parts.append(choice.delta.content)
            if choice is not None and choice.finish_reason:
                terminal = True
            if chunk.usage:
                usage = (
                    chunk.usage.model_dump()
                    if hasattr(chunk.usage, "model_dump")
                    else dict(chunk.usage)
                )
        e2e_ms = (perf_counter() - started) * 1000
        text = "".join(parts)
        status = "ok" if terminal and text else "incomplete"
        return StreamResult(
            status=status,
            ttft_ms=ttft_ms,
            e2e_ms=e2e_ms,
            output_text=text,
            chunk_count=chunk_count,
            terminal=terminal,
            usage=usage,
        )
    except Exception as exc:  # noqa: BLE001 — record per-request failure
        return StreamResult(
            status="error",
            ttft_ms=ttft_ms,
            e2e_ms=(perf_counter() - started) * 1000,
            output_text="".join(parts),
            chunk_count=chunk_count,
            terminal=terminal,
            error=str(exc),
        )


def iter_prompts(template: str, topics: list[str], count: int) -> Iterator[str]:
    if not topics:
        topics = ["distributed inference"]
    for index in range(count):
        yield template.format(topic=topics[index % len(topics)])
