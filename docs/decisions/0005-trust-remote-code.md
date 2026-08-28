# ADR 0005: trust_remote_code stays false

## Status

Accepted.

## Decision

`trust_remote_code=false` for both pinned models. vLLM 0.27.1 documents native Qwen3.5 hybrid support. If a specific model later fails to load without remote code, record the failure, the model revision, and a new ADR before enabling it.

## Consequences

Compose and serving config omit `--trust-remote-code` (a boolean flag would enable it if passed). Topology validation fails if the flag is turned on without an ADR.
