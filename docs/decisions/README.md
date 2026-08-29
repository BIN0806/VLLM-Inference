# Architecture decision records

ADRs explain why the system has its current shape. They are not transcripts of
an agent's private reasoning. They preserve the context and tradeoffs another
engineer would need to review, operate, or defend the design.

## Required sections

Every consequential ADR should contain:

1. **Status** — proposed, accepted, superseded, or rejected, including the gate.
2. **Context** — the constraint or problem that forced a choice.
3. **Decision** — the chosen behavior and its boundary.
4. **Alternatives considered** — at least the credible alternatives and why
   they were not selected for this gate.
5. **Evidence** — measurements, logs, documentation, or acceptance results that
   support the decision. Mark estimates as estimates.
6. **Consequences** — benefits, costs, risks, follow-up work, and claim limits.

## When an ADR is required

- Changing model, image, revision, CUDA, chart, or infrastructure pins.
- Changing TP, PP, Ray, replica, scheduling, storage, or autoscaling topology.
- Accepting a hardware exception or security exception.
- Enabling remote model code, public networking, credential transport, or TLS
  overrides.
- Choosing an autoscaling signal or changing the scale-to-zero boundary.
- Adopting a workaround that changes supported modalities, context, batching,
  memory use, or failure behavior.

Operational commands belong in runbooks. Raw logs and rental-specific details
belong in gitignored artifacts. System-level topology belongs in
`docs/architecture.md`.
