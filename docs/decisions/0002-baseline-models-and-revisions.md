# ADR 0002: Baseline models and immutable revisions

## Status

Accepted and used across the completed live gates.

## Decision

Two distinct models:

1. Portable and autoscaling baseline: `Qwen/Qwen2.5-1.5B-Instruct-AWQ`
   revision `3ecffa0ceb27851800f45519bab9c457a04405e1` (Apache-2.0). It was
   used for Phase 3, Phase 4, and the final Compose gate.
2. Single-GPU/TP validation model: `Qwen/Qwen3.5-9B` revision
   `c202236235762e1c871ad0ccb60c8ee5ba337b9a` (Apache-2.0). It was used
   for Phase 1 and Phase 2.

Do not silently change models. Fallback to the 1.5B AWQ model requires `ALLOW_MODEL_FALLBACK=true`, a prominent log, a report field, and cannot pass the originally requested model gate.

`trust_remote_code` remains false (see ADR 0005).

## Consequences

The 1.5B AWQ model is the portable regression, Kubernetes, and replica-scaling
model; it is not a 9B TP performance substitute. The 9B BF16 model requires
an explicit fit/topology gate and was not used for horizontal autoscaling.
