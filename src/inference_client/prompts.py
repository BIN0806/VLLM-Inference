"""Construct prompts that meet a configured input-token envelope."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptSpec:
    text: str
    topic: str
    target_tokens: int
    estimated_tokens: int
    meets_envelope: bool
    estimator: str = "max(whitespace_words, chars//4)"


def estimate_tokens(text: str) -> int:
    """Cheap offline estimate. Prefer server `usage.prompt_tokens` when available."""
    words = len(text.split())
    chars = max(1, (len(text) + 3) // 4)
    return max(words, chars)


def build_prompt(
    template: str,
    topic: str,
    target_tokens: int,
) -> PromptSpec:
    base = template.format(topic=topic)
    pieces = [base]
    serial = 0
    while estimate_tokens(" ".join(pieces)) < target_tokens:
        serial += 1
        pieces.append(f"Additional specified detail {serial:04d} regarding {topic}.")
        if serial > 10_000:
            break
    text = " ".join(pieces)
    estimated = estimate_tokens(text)
    return PromptSpec(
        text=text,
        topic=topic,
        target_tokens=target_tokens,
        estimated_tokens=estimated,
        meets_envelope=estimated >= target_tokens,
    )


def workload_token_label(*, nominal: int, estimated: int, measured: int | None) -> str:
    actual = measured if measured is not None else estimated
    if actual < int(nominal * 0.8):
        return f"short-prompt-envelope-not-met(nominal={nominal},actual={actual})"
    source = "measured" if measured is not None else "estimated"
    return f"{source}-prompt-tokens={actual}(nominal={nominal})"
