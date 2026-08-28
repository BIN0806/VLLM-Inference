# ADR 0002: Baseline models and immutable revisions

## Status

Accepted for Phase 0.

## Decision

Two distinct models:

1. Portable Phase 0/1 baseline: `Qwen/Qwen2.5-1.5B-Instruct-AWQ` revision `3ecffa0ceb27851800f45519bab9c457a04405e1` (Apache-2.0). Source: Hugging Face API `revision/main` on 2026-08-27.
2. Current RTX 3090 validation override: `Qwen/Qwen3.5-9B` revision `c202236235762e1c871ad0ccb60c8ee5ba337b9a` (Apache-2.0). Same discovery date.

Do not silently change models. Fallback to the 1.5B AWQ model requires `ALLOW_MODEL_FALLBACK=true`, a prominent log, a report field, and cannot pass the originally requested model gate.

`trust_remote_code` remains false (see ADR 0005).

## Consequences

The 1.5B AWQ model is for cheap regression, not TP performance studies. The 9B BF16 model is tight on 24 GiB; topology validation warns on headroom and fails if weights cannot fit.
