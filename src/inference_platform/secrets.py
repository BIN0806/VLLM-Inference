"""Secret redaction for logs, reports, and command summaries."""

from __future__ import annotations

import os
import re
from typing import Any

SECRET_ENV_NAMES = frozenset(
    {
        "VLLM_API_KEY",
        "HF_TOKEN",
        "HUGGING_FACE_HUB_TOKEN",
        "OPEN_BUTTON_TOKEN",
        "VAST_API_KEY",
        "GITHUB_TOKEN",
        "GH_TOKEN",
        "OPENAI_API_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AZURE_CLIENT_SECRET",
        "GOOGLE_APPLICATION_CREDENTIALS_JSON",
    }
)

_SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|access[_-]?token|hf[_-]?token|secret|password|passwd|authorization|credential)",
    re.IGNORECASE,
)
_METRIC_KEY_RE = re.compile(
    r"(prompt_tokens|completion_tokens|output_tokens|input_tokens|token_label|"
    r"typical_prompt|estimated_prompt|measured_prompt|tokens_per_sec)",
    re.IGNORECASE,
)
_REDACTED = "***REDACTED***"


def is_secret_name(name: str) -> bool:
    if _METRIC_KEY_RE.search(name):
        return False
    if name.upper() in SECRET_ENV_NAMES:
        return True
    return bool(_SECRET_KEY_RE.search(name))


def secret_env_values() -> set[str]:
    values: set[str] = set()
    for name, value in os.environ.items():
        if not value or not is_secret_name(name):
            continue
        if len(value) >= 4:
            values.add(value)
    return values


def redact_text(text: str, extra_values: set[str] | None = None) -> str:
    redacted = text
    values = secret_env_values()
    if extra_values:
        values |= {v for v in extra_values if v and len(v) >= 4}
    for value in sorted(values, key=len, reverse=True):
        redacted = redacted.replace(value, _REDACTED)
    return redacted


def redact_mapping(data: Any) -> Any:
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for key, value in data.items():
            if is_secret_name(str(key)):
                out[key] = _REDACTED if value else value
            else:
                out[key] = redact_mapping(value)
        return out
    if isinstance(data, list):
        return [redact_mapping(item) for item in data]
    if isinstance(data, str):
        return redact_text(data)
    return data
